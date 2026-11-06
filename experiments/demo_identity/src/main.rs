use argon2::{password_hash::SaltString, Argon2, PasswordHash, PasswordHasher, PasswordVerifier};
use axum::{
    extract::{ConnectInfo, DefaultBodyLimit, State},
    http::{HeaderMap, StatusCode},
    routing::{get, post},
    Json, Router,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use jsonwebtoken::{
    decode, decode_header, encode, Algorithm, DecodingKey, EncodingKey, Header, Validation,
};
use rand::rngs::OsRng;
use rsa::{
    pkcs8::{DecodePrivateKey, EncodePrivateKey, EncodePublicKey},
    traits::PublicKeyParts,
    RsaPrivateKey,
};
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    env, fs,
    io::{self, BufRead, Read, Write},
    net::SocketAddr,
    os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt},
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
    time::{Instant, SystemTime, UNIX_EPOCH},
};
use tokio::sync::Semaphore;
use uuid::Uuid;

const ACCESS_LIFETIME: i64 = 900;
const ADMIN_LIFETIME: i64 = 600;
const SCOPE: &str = "workstream:access";
const MAX_PASSWORD: usize = 1024;
type ApiError = (StatusCode, &'static str);
const INVALID: ApiError = (StatusCode::UNAUTHORIZED, "invalid credentials");

#[derive(Clone)]
struct App {
    db: Arc<Mutex<Connection>>,
    encoding: Arc<EncodingKey>,
    decoding: Arc<DecodingKey>,
    jwks: Arc<serde_json::Value>,
    issuer: String,
    audience: String,
    kid: String,
    work: Arc<Semaphore>,
    throttle: Arc<Mutex<Throttle>>,
    dummy_hash: String,
}
struct Throttle {
    started: Instant,
    global: u32,
    buckets: HashMap<String, (u32, Instant)>,
}
impl Throttle {
    fn allow(&mut self, key: String, limit: u32) -> bool {
        if self.started.elapsed().as_secs() >= 60 {
            self.started = Instant::now();
            self.global = 0;
            self.buckets.clear();
        }
        self.global += 1;
        if self.global > 1000 {
            return false;
        }
        if self.buckets.len() >= 2048 && !self.buckets.contains_key(&key) {
            if let Some(oldest) = self
                .buckets
                .iter()
                .min_by_key(|(_, (_, seen))| seen)
                .map(|(key, _)| key.clone())
            {
                self.buckets.remove(&oldest);
            }
        }
        let entry = self.buckets.entry(key).or_insert((0, Instant::now()));
        entry.0 += 1;
        entry.1 = Instant::now();
        entry.0 <= limit
    }
}
#[derive(Serialize, Deserialize)]
struct Claims {
    iss: String,
    sub: String,
    aud: String,
    iat: i64,
    nbf: i64,
    exp: i64,
    jti: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    subject_kind: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    scope: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    purpose: Option<String>,
}
#[derive(Deserialize)]
struct Credentials {
    email: String,
    password: String,
}
#[derive(Deserialize)]
struct PasswordChange {
    current_password: String,
    new_password: String,
}
#[derive(Serialize)]
struct LoginResponse {
    access_token: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    admin_token: Option<String>,
    token_type: &'static str,
    expires_in: i64,
}
#[derive(Serialize)]
struct AccountResponse {
    subject: String,
}

fn now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs() as i64
}
fn normalize_email(email: &str) -> Option<String> {
    let normalized = email.trim().to_ascii_lowercase();
    if normalized.len() > 254
        || normalized.len() < 3
        || !normalized.is_ascii()
        || normalized.contains(char::is_whitespace)
    {
        return None;
    }
    let (local, domain) = normalized.split_once('@')?;
    if local.is_empty()
        || domain.is_empty()
        || !domain.contains('.')
        || normalized.matches('@').count() != 1
    {
        return None;
    }
    Some(normalized)
}
fn password_ok(password: &str) -> bool {
    (12..=MAX_PASSWORD).contains(&password.len())
}
fn hash_password(password: &str) -> Result<String, String> {
    Argon2::default()
        .hash_password(password.as_bytes(), &SaltString::generate(&mut OsRng))
        .map(|h| h.to_string())
        .map_err(|_| "password hashing failed".into())
}
fn verify_password(password: &str, hash: &str) -> bool {
    PasswordHash::new(hash).ok().is_some_and(|parsed| {
        Argon2::default()
            .verify_password(password.as_bytes(), &parsed)
            .is_ok()
    })
}
fn private_file(path: &Path) -> Result<Vec<u8>, String> {
    let meta = private_metadata(path)?;
    if meta.len() > 65536 {
        return Err("unsafe private file".into());
    }
    fs::read(path).map_err(|_| "cannot read private file".into())
}
fn private_metadata(path: &Path) -> Result<fs::Metadata, String> {
    let meta = fs::symlink_metadata(path).map_err(|_| "missing private file")?;
    if !meta.is_file() || meta.permissions().mode() & 0o077 != 0 {
        return Err("unsafe private file".into());
    }
    Ok(meta)
}
fn write_private(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)
        .map_err(|_| "cannot create private file")?;
    file.write_all(bytes)
        .map_err(|_| String::from("cannot write private file"))?;
    file.sync_all()
        .map_err(|_| "cannot sync private file".into())
}
fn database(path: &Path) -> Result<Connection, String> {
    private_metadata(path)?;
    let db = Connection::open(path).map_err(|_| "cannot open database")?;
    db.busy_timeout(std::time::Duration::from_secs(3))
        .map_err(|_| "database timeout failed")?;
    Ok(db)
}
fn init(dir: &Path, email: &str) -> Result<(), String> {
    let mut password = Vec::new();
    io::BufReader::new(io::stdin().lock().take(1025))
        .read_until(b'\n', &mut password)
        .map_err(|_| "cannot read password")?;
    let password = String::from_utf8(password).map_err(|_| "invalid password encoding")?;
    initialize(dir, email, password.trim_end_matches(['\n', '\r']))
}
fn initialize(dir: &Path, email: &str, password: &str) -> Result<(), String> {
    let email = normalize_email(email).ok_or("invalid email")?;
    if !password_ok(password) {
        return Err("password must be 12 to 1024 bytes".into());
    }
    let hash = hash_password(password)?;
    let mut builder = fs::DirBuilder::new();
    builder.mode(0o700);
    builder
        .create(dir)
        .map_err(|_| "issuer directory already exists or cannot be created")?;
    let key = RsaPrivateKey::new(&mut OsRng, 3072).map_err(|_| "key generation failed")?;
    let pem = key
        .to_pkcs8_pem(rsa::pkcs8::LineEnding::LF)
        .map_err(|_| "key encoding failed")?;
    write_private(&dir.join("signer.pem"), pem.as_bytes())?;
    let mut db =
        Connection::open(dir.join("accounts.db")).map_err(|_| "database creation failed")?;
    fs::set_permissions(dir.join("accounts.db"), fs::Permissions::from_mode(0o600))
        .map_err(|_| "database permission failed")?;
    db.execute_batch("PRAGMA journal_mode=DELETE; CREATE TABLE accounts (subject TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL CHECK(is_admin IN (0,1))); CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);").map_err(|_| "schema creation failed")?;
    let tx = db
        .transaction()
        .map_err(|_| "database transaction failed")?;
    tx.execute(
        "INSERT INTO accounts VALUES (?1, ?2, ?3, 1)",
        params![Uuid::new_v4().to_string(), email, hash],
    )
    .map_err(|_| "admin creation failed")?;
    tx.execute(
        "INSERT INTO metadata VALUES ('dummy_hash', ?1)",
        [hash_password("not-a-real-account-password")?],
    )
    .map_err(|_| "metadata creation failed")?;
    tx.commit().map_err(|_| "database commit failed")?;
    println!("issuer initialized");
    Ok(())
}
fn read_app(dir: &Path, issuer: String, audience: String) -> Result<App, String> {
    if !issuer.starts_with("https://")
        || issuer.contains(['?', '#', '@'])
        || audience.is_empty()
        || audience.contains(char::is_whitespace)
    {
        return Err("invalid issuer configuration".into());
    }
    let meta = fs::symlink_metadata(dir).map_err(|_| "missing issuer directory")?;
    if !meta.is_dir() || meta.permissions().mode() & 0o077 != 0 {
        return Err("unsafe issuer directory".into());
    }
    let signer = private_file(&dir.join("signer.pem"))?;
    let key =
        RsaPrivateKey::from_pkcs8_pem(std::str::from_utf8(&signer).map_err(|_| "invalid signer")?)
            .map_err(|_| "invalid signer")?;
    if key.n().bits() < 2048 {
        return Err("weak signer".into());
    }
    let public_der = key
        .to_public_key()
        .to_public_key_der()
        .map_err(|_| "invalid public key")?;
    let kid = format!("{:x}", Sha256::digest(public_der.as_bytes()));
    let jwks = serde_json::json!({"keys":[{"kty":"RSA","kid":kid,"use":"sig","key_ops":["verify"],"alg":"RS256","n":URL_SAFE_NO_PAD.encode(key.n().to_bytes_be()),"e":URL_SAFE_NO_PAD.encode(key.e().to_bytes_be())}]});
    let public_pem = key
        .to_public_key()
        .to_public_key_pem(rsa::pkcs8::LineEnding::LF)
        .map_err(|_| "invalid public key")?;
    let db = database(&dir.join("accounts.db"))?;
    let dummy_hash: String = db
        .query_row(
            "SELECT value FROM metadata WHERE key='dummy_hash'",
            [],
            |r| r.get(0),
        )
        .map_err(|_| "missing metadata")?;
    PasswordHash::new(&dummy_hash).map_err(|_| "invalid metadata")?;
    db.query_row("SELECT COUNT(*) FROM accounts WHERE is_admin=1", [], |r| {
        r.get::<_, i64>(0)
    })
    .map_err(|_| "invalid accounts")?
    .gt(&0)
    .then_some(())
    .ok_or("missing administrator")?;
    Ok(App {
        db: Arc::new(Mutex::new(db)),
        encoding: Arc::new(EncodingKey::from_rsa_pem(&signer).map_err(|_| "invalid signer")?),
        decoding: Arc::new(
            DecodingKey::from_rsa_pem(public_pem.as_bytes()).map_err(|_| "invalid public key")?,
        ),
        jwks: Arc::new(jwks),
        issuer,
        audience,
        kid,
        work: Arc::new(Semaphore::new(4)),
        throttle: Arc::new(Mutex::new(Throttle {
            started: Instant::now(),
            global: 0,
            buckets: HashMap::new(),
        })),
        dummy_hash,
    })
}
fn token(app: &App, sub: &str, admin: bool) -> Result<String, ApiError> {
    let issued = now();
    let claims = Claims {
        iss: app.issuer.clone(),
        sub: sub.to_owned(),
        aud: if admin {
            format!("{}:issuer-admin", app.audience)
        } else {
            app.audience.clone()
        },
        iat: issued,
        nbf: issued,
        exp: issued
            + if admin {
                ADMIN_LIFETIME
            } else {
                ACCESS_LIFETIME
            },
        jti: Uuid::new_v4().to_string(),
        subject_kind: if admin { None } else { Some("human".into()) },
        scope: if admin { None } else { Some(SCOPE.into()) },
        purpose: if admin {
            Some("issuer_admin".into())
        } else {
            None
        },
    };
    let mut header = Header::new(Algorithm::RS256);
    header.kid = Some(app.kid.clone());
    encode(&header, &claims, &app.encoding)
        .map_err(|_| (StatusCode::INTERNAL_SERVER_ERROR, "token issuance failed"))
}
fn authenticate(app: &App, headers: &HeaderMap, admin: bool) -> Result<String, ApiError> {
    let value = headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .ok_or(INVALID)?;
    if value.len() > 8192 {
        return Err(INVALID);
    }
    let header = decode_header(value).map_err(|_| INVALID)?;
    if header.alg != Algorithm::RS256 || header.kid.as_deref() != Some(app.kid.as_str()) {
        return Err(INVALID);
    }
    let mut validation = Validation::new(Algorithm::RS256);
    validation.leeway = 0;
    validation.validate_nbf = true;
    validation.set_issuer(&[&app.issuer]);
    validation.set_audience(&[if admin {
        format!("{}:issuer-admin", app.audience)
    } else {
        app.audience.clone()
    }]);
    validation
        .required_spec_claims
        .extend(["iat".into(), "nbf".into(), "jti".into()]);
    let decoded = decode::<Claims>(value, &app.decoding, &validation).map_err(|_| INVALID)?;
    if decoded.claims.iat > now() || decoded.claims.nbf > now() || decoded.claims.exp <= now() {
        return Err(INVALID);
    }
    if decoded.claims.purpose.as_deref() != if admin { Some("issuer_admin") } else { None } {
        return Err(INVALID);
    }
    if !admin
        && (decoded.claims.subject_kind.as_deref() != Some("human")
            || decoded.claims.scope.as_deref() != Some(SCOPE))
    {
        return Err(INVALID);
    }
    Ok(decoded.claims.sub)
}
fn throttled(app: &App, key: String, limit: u32) -> Result<(), ApiError> {
    if app.throttle.lock().unwrap().allow(key, limit) {
        Ok(())
    } else {
        Err((StatusCode::TOO_MANY_REQUESTS, "try later"))
    }
}
async fn jwks(State(app): State<App>) -> Json<serde_json::Value> {
    Json((*app.jwks).clone())
}
async fn login(
    State(app): State<App>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    Json(input): Json<Credentials>,
) -> Result<Json<LoginResponse>, ApiError> {
    throttled(&app, format!("ip:{}", peer.ip()), 60)?;
    let email = normalize_email(&input.email).ok_or(INVALID)?;
    throttled(&app, format!("email:{email}"), 10)?;
    if !password_ok(&input.password) {
        return Err(INVALID);
    }
    let _permit = app
        .work
        .clone()
        .try_acquire_owned()
        .map_err(|_| (StatusCode::TOO_MANY_REQUESTS, "try later"))?;
    let copy = app.clone();
    let result = tokio::task::spawn_blocking(move || {
        let db = copy.db.lock().unwrap();
        let account: Option<(String, String, i64)> = db
            .query_row(
                "SELECT subject,password_hash,is_admin FROM accounts WHERE email=?1",
                [email],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
            )
            .optional()
            .ok()
            .flatten();
        let candidate = account
            .as_ref()
            .map(|a| a.1.as_str())
            .unwrap_or(&copy.dummy_hash);
        if !verify_password(&input.password, candidate) {
            return None;
        }
        account.map(|(sub, _, admin)| (sub, admin == 1))
    })
    .await
    .map_err(|_| INVALID)?
    .ok_or(INVALID)?;
    Ok(Json(LoginResponse {
        access_token: token(&app, &result.0, false)?,
        admin_token: if result.1 {
            Some(token(&app, &result.0, true)?)
        } else {
            None
        },
        token_type: "Bearer",
        expires_in: ACCESS_LIFETIME,
    }))
}
async fn create_account(
    State(app): State<App>,
    headers: HeaderMap,
    Json(input): Json<Credentials>,
) -> Result<(StatusCode, Json<AccountResponse>), ApiError> {
    let admin_sub = authenticate(&app, &headers, true)?;
    throttled(&app, format!("admin:{admin_sub}"), 20)?;
    let email =
        normalize_email(&input.email).ok_or((StatusCode::BAD_REQUEST, "invalid account input"))?;
    if !password_ok(&input.password) {
        return Err((StatusCode::BAD_REQUEST, "invalid account input"));
    }
    let _permit = app
        .work
        .clone()
        .try_acquire_owned()
        .map_err(|_| (StatusCode::TOO_MANY_REQUESTS, "try later"))?;
    let copy = app.clone();
    let result = tokio::task::spawn_blocking(move || {
        let hash = hash_password(&input.password)
            .map_err(|_| (StatusCode::INTERNAL_SERVER_ERROR, "account unavailable"))?;
        let subject = Uuid::new_v4().to_string();
        let mut db = copy.db.lock().unwrap();
        let tx = db
            .transaction()
            .map_err(|_| (StatusCode::SERVICE_UNAVAILABLE, "account unavailable"))?;
        let is_admin: i64 = tx
            .query_row(
                "SELECT is_admin FROM accounts WHERE subject=?1",
                [admin_sub],
                |r| r.get(0),
            )
            .map_err(|_| INVALID)?;
        if is_admin != 1 {
            return Err(INVALID);
        }
        tx.execute(
            "INSERT INTO accounts VALUES (?1,?2,?3,0)",
            params![subject, email, hash],
        )
        .map_err(|_| (StatusCode::CONFLICT, "account unavailable"))?;
        tx.commit()
            .map_err(|_| (StatusCode::SERVICE_UNAVAILABLE, "account unavailable"))?;
        Ok(subject)
    })
    .await
    .map_err(|_| (StatusCode::SERVICE_UNAVAILABLE, "account unavailable"))??;
    Ok((
        StatusCode::CREATED,
        Json(AccountResponse { subject: result }),
    ))
}
async fn change_password(
    State(app): State<App>,
    headers: HeaderMap,
    Json(input): Json<PasswordChange>,
) -> Result<StatusCode, ApiError> {
    let sub = authenticate(&app, &headers, false)?;
    throttled(&app, format!("password:{sub}"), 10)?;
    if !password_ok(&input.current_password) || !password_ok(&input.new_password) {
        return Err(INVALID);
    }
    let _permit = app
        .work
        .clone()
        .try_acquire_owned()
        .map_err(|_| (StatusCode::TOO_MANY_REQUESTS, "try later"))?;
    let copy = app.clone();
    tokio::task::spawn_blocking(move || {
        let mut db = copy.db.lock().unwrap();
        let tx = db.transaction().map_err(|_| INVALID)?;
        let current: String = tx
            .query_row(
                "SELECT password_hash FROM accounts WHERE subject=?1",
                [&sub],
                |r| r.get(0),
            )
            .map_err(|_| INVALID)?;
        if !verify_password(&input.current_password, &current) {
            return Err(INVALID);
        }
        let replacement = hash_password(&input.new_password).map_err(|_| INVALID)?;
        tx.execute(
            "UPDATE accounts SET password_hash=?1 WHERE subject=?2",
            params![replacement, sub],
        )
        .map_err(|_| INVALID)?;
        tx.commit().map_err(|_| INVALID)?;
        Ok::<_, ApiError>(())
    })
    .await
    .map_err(|_| INVALID)??;
    Ok(StatusCode::NO_CONTENT)
}
#[tokio::main]
async fn main() {
    if let Err(error) = run().await {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
async fn run() -> Result<(), String> {
    let args: Vec<String> = env::args().collect();
    match args.as_slice() {
        [_, command, dir, email] if command == "init" => init(Path::new(dir), email),
        [_, command, dir] if command == "serve" => {
            let issuer = env::var("DEMO_IDENTITY_ISSUER").map_err(|_| "missing issuer")?;
            let audience = env::var("DEMO_IDENTITY_AUDIENCE").map_err(|_| "missing audience")?;
            let cert = PathBuf::from(
                env::var("DEMO_IDENTITY_TLS_CERT").map_err(|_| "missing certificate path")?,
            );
            let key = PathBuf::from(
                env::var("DEMO_IDENTITY_TLS_KEY").map_err(|_| "missing TLS key path")?,
            );
            private_file(&key)?;
            let app = read_app(Path::new(dir), issuer, audience)?;
            let router = Router::new()
                .route("/jwks.json", get(jwks))
                .route("/login", post(login))
                .route("/admin/accounts", post(create_account))
                .route("/me/password", post(change_password))
                .layer(DefaultBodyLimit::max(4096))
                .with_state(app);
            let config = axum_server::tls_rustls::RustlsConfig::from_pem_file(cert, key)
                .await
                .map_err(|_| "invalid TLS material")?;
            let bind: SocketAddr = env::var("DEMO_IDENTITY_BIND")
                .unwrap_or("127.0.0.1:8443".into())
                .parse()
                .map_err(|_| "invalid bind address")?;
            axum_server::bind_rustls(bind, config)
                .serve(router.into_make_service_with_connect_info::<SocketAddr>())
                .await
                .map_err(|_| "issuer server failed".into())
        }
        _ => Err(
            "usage: demo-identity init DATA_DIR ADMIN_EMAIL < password-on-stdin | serve DATA_DIR"
                .into(),
        ),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::extract::State;
    async fn login(
        state: State<App>,
        input: Json<Credentials>,
    ) -> Result<Json<LoginResponse>, ApiError> {
        super::login(state, ConnectInfo("127.0.0.1:1234".parse().unwrap()), input).await
    }
    fn bearer(value: &str) -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert("authorization", format!("Bearer {value}").parse().unwrap());
        headers
    }
    fn fixture() -> (tempfile::TempDir, App) {
        let parent = tempfile::tempdir().unwrap();
        let dir = parent.path().join("issuer");
        initialize(&dir, "ADMIN@EXAMPLE.TEST", "initial-password-123").unwrap();
        let app = read_app(
            &dir,
            "https://demo.example.test".into(),
            "workstream-demo".into(),
        )
        .unwrap();
        (parent, app)
    }
    #[tokio::test]
    async fn admin_provisions_user_but_access_token_cannot_administer() {
        let (_dir, app) = fixture();
        let Json(admin) = login(
            State(app.clone()),
            Json(Credentials {
                email: "admin@example.test".into(),
                password: "initial-password-123".into(),
            }),
        )
        .await
        .unwrap();
        assert!(admin.admin_token.is_some());
        assert_eq!(
            create_account(
                State(app.clone()),
                bearer(&admin.access_token),
                Json(Credentials {
                    email: "user@example.test".into(),
                    password: "user-password-123".into()
                })
            )
            .await
            .err()
            .unwrap()
            .0,
            StatusCode::UNAUTHORIZED
        );
        let (_, Json(created)) = create_account(
            State(app.clone()),
            bearer(admin.admin_token.as_ref().unwrap()),
            Json(Credentials {
                email: "USER@example.test".into(),
                password: "user-password-123".into(),
            }),
        )
        .await
        .unwrap();
        assert_eq!(
            create_account(
                State(app.clone()),
                bearer(admin.admin_token.as_ref().unwrap()),
                Json(Credentials {
                    email: "user@example.test".into(),
                    password: "different-password-123".into()
                })
            )
            .await
            .err()
            .unwrap()
            .0,
            StatusCode::CONFLICT
        );
        let Json(user) = login(
            State(app.clone()),
            Json(Credentials {
                email: "user@example.test".into(),
                password: "user-password-123".into(),
            }),
        )
        .await
        .unwrap();
        assert!(user.admin_token.is_none());
        assert_eq!(
            authenticate(&app, &bearer(&user.access_token), false).unwrap(),
            created.subject
        );
        assert!(authenticate(&app, &bearer(&user.access_token), true).is_err());
        assert!(authenticate(&app, &bearer(admin.admin_token.as_ref().unwrap()), false).is_err());
        let permits: Vec<_> = (0..4)
            .map(|_| app.work.clone().try_acquire_owned().unwrap())
            .collect();
        assert_eq!(
            login(
                State(app.clone()),
                Json(Credentials {
                    email: "user@example.test".into(),
                    password: "user-password-123".into(),
                })
            )
            .await
            .err()
            .unwrap()
            .0,
            StatusCode::TOO_MANY_REQUESTS
        );
        drop(permits);
        app.throttle
            .lock()
            .unwrap()
            .buckets
            .insert("email:user@example.test".into(), (10, Instant::now()));
        assert_eq!(
            login(
                State(app.clone()),
                Json(Credentials {
                    email: "user@example.test".into(),
                    password: "user-password-123".into(),
                })
            )
            .await
            .err()
            .unwrap()
            .0,
            StatusCode::TOO_MANY_REQUESTS
        );
        assert!(login(
            State(app.clone()),
            Json(Credentials {
                email: "admin@example.test".into(),
                password: "initial-password-123".into(),
            })
        )
        .await
        .is_ok());
        app.throttle
            .lock()
            .unwrap()
            .buckets
            .remove("email:user@example.test");
        app.db
            .lock()
            .unwrap()
            .execute(
                "UPDATE accounts SET is_admin=0 WHERE email='admin@example.test'",
                [],
            )
            .unwrap();
        assert_eq!(
            create_account(
                State(app.clone()),
                bearer(admin.admin_token.as_ref().unwrap()),
                Json(Credentials {
                    email: "other@example.test".into(),
                    password: "other-password-123".into(),
                })
            )
            .await
            .err()
            .unwrap()
            .0,
            StatusCode::UNAUTHORIZED
        );
        app.db
            .lock()
            .unwrap()
            .execute(
                "UPDATE accounts SET is_admin=1 WHERE email='admin@example.test'",
                [],
            )
            .unwrap();
        let reopened = read_app(
            &_dir.path().join("issuer"),
            app.issuer.clone(),
            app.audience.clone(),
        )
        .unwrap();
        let Json(after_restart) = login(
            State(reopened),
            Json(Credentials {
                email: "user@example.test".into(),
                password: "user-password-123".into(),
            }),
        )
        .await
        .unwrap();
        assert_eq!(
            authenticate(&app, &bearer(&after_restart.access_token), false).unwrap(),
            created.subject
        );
    }
    #[tokio::test]
    async fn password_change_requires_current_password_and_preserves_subject() {
        let (_dir, app) = fixture();
        let Json(admin) = login(
            State(app.clone()),
            Json(Credentials {
                email: "admin@example.test".into(),
                password: "initial-password-123".into(),
            }),
        )
        .await
        .unwrap();
        let wrong = change_password(
            State(app.clone()),
            bearer(&admin.access_token),
            Json(PasswordChange {
                current_password: "wrong-password-123".into(),
                new_password: "changed-password-123".into(),
            }),
        )
        .await;
        assert_eq!(wrong.unwrap_err().0, StatusCode::UNAUTHORIZED);
        change_password(
            State(app.clone()),
            bearer(&admin.access_token),
            Json(PasswordChange {
                current_password: "initial-password-123".into(),
                new_password: "changed-password-123".into(),
            }),
        )
        .await
        .unwrap();
        assert!(login(
            State(app.clone()),
            Json(Credentials {
                email: "admin@example.test".into(),
                password: "initial-password-123".into()
            })
        )
        .await
        .is_err());
        let Json(next) = login(
            State(app.clone()),
            Json(Credentials {
                email: "admin@example.test".into(),
                password: "changed-password-123".into(),
            }),
        )
        .await
        .unwrap();
        assert_eq!(
            authenticate(&app, &bearer(&next.access_token), false).unwrap(),
            authenticate(&app, &bearer(&admin.access_token), false).unwrap()
        );
    }
    #[test]
    fn fail_closed_on_missing_state_and_nonprivate_key() {
        let (dir, app) = fixture();
        assert!(read_app(
            &dir.path().join("missing"),
            app.issuer.clone(),
            app.audience.clone()
        )
        .is_err());
        fs::set_permissions(
            dir.path().join("issuer/signer.pem"),
            fs::Permissions::from_mode(0o644),
        )
        .unwrap();
        assert!(read_app(&dir.path().join("issuer"), app.issuer, app.audience).is_err());
    }
}
