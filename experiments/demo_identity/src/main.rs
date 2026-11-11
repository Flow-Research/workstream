use argon2::{password_hash::SaltString, Argon2, PasswordHash, PasswordHasher, PasswordVerifier};
use axum::{
    extract::{DefaultBodyLimit, State},
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
const ROTATION_LIFETIME: i64 = 300;
const SCHEMA_VERSION: i64 = 1;
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
    #[serde(skip_serializing_if = "Option::is_none")]
    email: Option<String>,
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
    #[serde(skip_serializing_if = "Option::is_none")]
    access_token: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    password_change_token: Option<String>,
    must_change_password: bool,
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
    db.execute_batch("PRAGMA journal_mode=DELETE; CREATE TABLE accounts (subject TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL CHECK(is_admin IN (0,1)), must_change_password INTEGER NOT NULL CHECK(must_change_password IN (0,1))); CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);").map_err(|_| "schema creation failed")?;
    let tx = db
        .transaction()
        .map_err(|_| "database transaction failed")?;
    tx.execute(
        "INSERT INTO accounts VALUES (?1, ?2, ?3, 1, 0)",
        params![Uuid::new_v4().to_string(), email, hash],
    )
    .map_err(|_| "admin creation failed")?;
    tx.execute(
        "INSERT INTO metadata VALUES ('dummy_hash', ?1)",
        [hash_password("not-a-real-account-password")?],
    )
    .map_err(|_| "metadata creation failed")?;
    tx.pragma_update(None, "user_version", SCHEMA_VERSION)
        .map_err(|_| "schema version failed")?;
    tx.commit().map_err(|_| "database commit failed")?;
    println!("issuer initialized");
    Ok(())
}
// Version zero is the original retained schema. Never migrate while serving.
fn upgrade(dir: &Path) -> Result<(), String> {
    let meta = fs::symlink_metadata(dir).map_err(|_| "missing issuer directory")?;
    if !meta.is_dir() || meta.permissions().mode() & 0o077 != 0 {
        return Err("unsafe issuer directory".into());
    }
    private_file(&dir.join("signer.pem"))?;
    let mut db = database(&dir.join("accounts.db"))?;
    let tx = db
        .transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)
        .map_err(|_| "upgrade transaction failed")?;
    let version: i64 = tx
        .pragma_query_value(None, "user_version", |r| r.get(0))
        .map_err(|_| "schema version unavailable")?;
    match version {
        0 => {
            tx.execute_batch("ALTER TABLE accounts ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0 CHECK(must_change_password IN (0,1)); UPDATE accounts SET must_change_password=1 WHERE is_admin=0;")
                .map_err(|_| "schema upgrade failed")?;
            tx.pragma_update(None, "user_version", SCHEMA_VERSION)
                .map_err(|_| "schema version failed")?;
        }
        SCHEMA_VERSION => {}
        _ => return Err("unsupported schema version".into()),
    }
    tx.commit().map_err(|_| "upgrade commit failed")?;
    println!("issuer schema current");
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
    let version: i64 = db
        .pragma_query_value(None, "user_version", |r| r.get(0))
        .map_err(|_| "schema version unavailable")?;
    if version != SCHEMA_VERSION {
        return Err("issuer schema requires explicit upgrade DATA_DIR".into());
    }
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
#[derive(Clone, Copy, PartialEq)]
enum TokenKind {
    Access,
    Admin,
    PasswordChange,
}
impl TokenKind {
    fn audience(self, app: &App) -> String {
        match self {
            Self::Access => app.audience.clone(),
            Self::Admin => format!("{}:issuer-admin", app.audience),
            Self::PasswordChange => format!("{}:password-change", app.audience),
        }
    }
    fn purpose(self) -> Option<&'static str> {
        match self {
            Self::Access => None,
            Self::Admin => Some("issuer_admin"),
            Self::PasswordChange => Some("password_change"),
        }
    }
    fn lifetime(self) -> i64 {
        match self {
            Self::Access => ACCESS_LIFETIME,
            Self::Admin => ADMIN_LIFETIME,
            Self::PasswordChange => ROTATION_LIFETIME,
        }
    }
}
fn token(app: &App, sub: &str, kind: TokenKind, email: &str) -> Result<String, ApiError> {
    let issued = now();
    let claims = Claims {
        iss: app.issuer.clone(),
        sub: sub.to_owned(),
        email: if kind == TokenKind::Access {
            Some(email.to_owned())
        } else {
            None
        },
        aud: kind.audience(app),
        iat: issued,
        nbf: issued,
        exp: issued + kind.lifetime(),
        jti: Uuid::new_v4().to_string(),
        subject_kind: if kind == TokenKind::Access {
            Some("human".into())
        } else {
            None
        },
        scope: if kind == TokenKind::Access {
            Some(SCOPE.into())
        } else {
            None
        },
        purpose: kind.purpose().map(str::to_owned),
    };
    let mut header = Header::new(Algorithm::RS256);
    header.kid = Some(app.kid.clone());
    encode(&header, &claims, &app.encoding)
        .map_err(|_| (StatusCode::INTERNAL_SERVER_ERROR, "token issuance failed"))
}
fn authenticate(app: &App, headers: &HeaderMap, admin: bool) -> Result<String, ApiError> {
    authenticate_kind(
        app,
        headers,
        if admin {
            TokenKind::Admin
        } else {
            TokenKind::Access
        },
    )
}
fn authenticate_kind(app: &App, headers: &HeaderMap, kind: TokenKind) -> Result<String, ApiError> {
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
    validation.set_audience(&[kind.audience(app)]);
    validation
        .required_spec_claims
        .extend(["iat".into(), "nbf".into(), "jti".into()]);
    let decoded = decode::<Claims>(value, &app.decoding, &validation).map_err(|_| INVALID)?;
    if decoded.claims.iat > now() || decoded.claims.nbf > now() || decoded.claims.exp <= now() {
        return Err(INVALID);
    }
    if decoded.claims.purpose.as_deref() != kind.purpose() {
        return Err(INVALID);
    }
    if kind == TokenKind::Access
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
    Json(input): Json<Credentials>,
) -> Result<Json<LoginResponse>, ApiError> {
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
        let account: Option<(String, String, i64, i64, String)> = {
            let db = copy.db.lock().unwrap();
            db.query_row(
                "SELECT subject,password_hash,is_admin,must_change_password,email FROM accounts WHERE email=?1",
                [email],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)),
            )
            .optional()
            .ok()
            .flatten()
        };
        let candidate = account
            .as_ref()
            .map(|a| a.1.as_str())
            .unwrap_or(&copy.dummy_hash);
        if !verify_password(&input.password, candidate) {
            return None;
        }
        account.map(|(sub, _, admin, pending, email)| (sub, admin == 1, pending == 1, email))
    })
    .await
    .map_err(|_| INVALID)?
    .ok_or(INVALID)?;
    Ok(Json(LoginResponse {
        access_token: if result.2 {
            None
        } else {
            Some(token(&app, &result.0, TokenKind::Access, &result.3)?)
        },
        password_change_token: if result.2 {
            Some(token(
                &app,
                &result.0,
                TokenKind::PasswordChange,
                &result.3,
            )?)
        } else {
            None
        },
        must_change_password: result.2,
        admin_token: if result.1 && !result.2 {
            Some(token(&app, &result.0, TokenKind::Admin, &result.3)?)
        } else {
            None
        },
        token_type: "Bearer",
        expires_in: if result.2 {
            ROTATION_LIFETIME
        } else {
            ACCESS_LIFETIME
        },
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
            "INSERT INTO accounts (subject,email,password_hash,is_admin,must_change_password) VALUES (?1,?2,?3,0,1)",
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
fn replace_password_hash(
    db: &Connection,
    subject: &str,
    current: &str,
    replacement: &str,
    pending: bool,
) -> Result<(), ApiError> {
    let changed = db
        .execute(
            "UPDATE accounts SET password_hash=?1,must_change_password=0 WHERE subject=?2 AND password_hash=?3 AND must_change_password=?4",
            params![replacement, subject, current, pending],
        )
        .map_err(|_| INVALID)?;
    if changed != 1 {
        return Err(INVALID);
    }
    Ok(())
}
async fn change_password(
    State(app): State<App>,
    headers: HeaderMap,
    Json(input): Json<PasswordChange>,
) -> Result<StatusCode, ApiError> {
    let (sub, pending) = match authenticate_kind(&app, &headers, TokenKind::PasswordChange) {
        Ok(sub) => (sub, true),
        Err(_) => (authenticate(&app, &headers, false)?, false),
    };
    throttled(&app, format!("password:{sub}"), 10)?;
    if !password_ok(&input.current_password)
        || !password_ok(&input.new_password)
        || input.current_password == input.new_password
    {
        return Err(INVALID);
    }
    let _permit = app
        .work
        .clone()
        .try_acquire_owned()
        .map_err(|_| (StatusCode::TOO_MANY_REQUESTS, "try later"))?;
    let copy = app.clone();
    tokio::task::spawn_blocking(move || {
        let current: String = {
            let db = copy.db.lock().unwrap();
            db.query_row(
                "SELECT password_hash FROM accounts WHERE subject=?1 AND must_change_password=?2",
                params![sub, pending],
                |r| r.get(0),
            )
            .map_err(|_| INVALID)?
        };
        if !verify_password(&input.current_password, &current) {
            return Err(INVALID);
        }
        let replacement = hash_password(&input.new_password).map_err(|_| INVALID)?;
        let db = copy.db.lock().unwrap();
        replace_password_hash(&db, &sub, &current, &replacement, pending)
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
        [_, command, dir] if command == "upgrade" => upgrade(Path::new(dir)),
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
                .serve(router.into_make_service())
                .await
                .map_err(|_| "issuer server failed".into())
        }
        _ => Err(
            "usage: demo-identity init DATA_DIR ADMIN_EMAIL < password-on-stdin | upgrade DATA_DIR | serve DATA_DIR"
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
        super::login(state, input).await
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
    fn signed_claims(app: &App, value: &str, kind: TokenKind) -> serde_json::Value {
        let mut validation = Validation::new(Algorithm::RS256);
        validation.set_issuer(&[&app.issuer]);
        validation.set_audience(&[kind.audience(app)]);
        decode::<serde_json::Value>(value, &app.decoding, &validation)
            .unwrap()
            .claims
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
        let admin_access = signed_claims(
            &app,
            admin.access_token.as_deref().unwrap(),
            TokenKind::Access,
        );
        let admin_only = signed_claims(
            &app,
            admin.admin_token.as_deref().unwrap(),
            TokenKind::Admin,
        );
        assert_eq!(admin_access["email"], "admin@example.test");
        assert_eq!(admin_access["sub"], admin_only["sub"]);
        assert!(admin_access.get("email_verified").is_none());
        assert!(admin_only.get("email").is_none());
        assert!(admin_only.get("email_verified").is_none());
        assert_eq!(
            create_account(
                State(app.clone()),
                bearer(admin.access_token.as_deref().unwrap()),
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
        assert!(user.access_token.is_none());
        let rotation = user.password_change_token.unwrap();
        let restricted = signed_claims(&app, &rotation, TokenKind::PasswordChange);
        assert!(restricted.get("email").is_none());
        assert!(restricted.get("email_verified").is_none());
        assert!(authenticate(&app, &bearer(&rotation), false).is_err());
        assert!(authenticate(&app, &bearer(&rotation), true).is_err());
        let same = change_password(
            State(app.clone()),
            bearer(&rotation),
            Json(PasswordChange {
                current_password: "user-password-123".into(),
                new_password: "user-password-123".into(),
            }),
        )
        .await;
        assert_eq!(same.unwrap_err(), INVALID);
        change_password(
            State(app.clone()),
            bearer(&rotation),
            Json(PasswordChange {
                current_password: "user-password-123".into(),
                new_password: "chosen-password-123".into(),
            }),
        )
        .await
        .unwrap();
        // Even knowledge of the new password cannot reuse a consumed rotation token.
        assert_eq!(
            change_password(
                State(app.clone()),
                bearer(&rotation),
                Json(PasswordChange {
                    current_password: "chosen-password-123".into(),
                    new_password: "another-password-123".into(),
                })
            )
            .await
            .unwrap_err(),
            INVALID
        );
        let Json(user) = login(
            State(app.clone()),
            Json(Credentials {
                email: " USER@EXAMPLE.TEST ".into(),
                password: "chosen-password-123".into(),
            }),
        )
        .await
        .unwrap();
        assert_eq!(
            authenticate(&app, &bearer(user.access_token.as_deref().unwrap()), false).unwrap(),
            created.subject
        );
        let access = signed_claims(
            &app,
            user.access_token.as_deref().unwrap(),
            TokenKind::Access,
        );
        let stored_email: String = app
            .db
            .lock()
            .unwrap()
            .query_row(
                "SELECT email FROM accounts WHERE subject=?1",
                [&created.subject],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(access["email"], stored_email);
        assert_eq!(stored_email, "user@example.test");
        assert_eq!(access["sub"], restricted["sub"]);
        assert_eq!(access["sub"], created.subject);
        assert!(access.get("email_verified").is_none());
        assert!(authenticate(&app, &bearer(user.access_token.as_deref().unwrap()), true).is_err());
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
                password: "chosen-password-123".into(),
            }),
        )
        .await
        .unwrap();
        assert_eq!(
            authenticate(
                &app,
                &bearer(after_restart.access_token.as_deref().unwrap()),
                false
            )
            .unwrap(),
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
            bearer(admin.access_token.as_deref().unwrap()),
            Json(PasswordChange {
                current_password: "wrong-password-123".into(),
                new_password: "changed-password-123".into(),
            }),
        )
        .await;
        assert_eq!(wrong.unwrap_err().0, StatusCode::UNAUTHORIZED);
        change_password(
            State(app.clone()),
            bearer(admin.access_token.as_deref().unwrap()),
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
            authenticate(&app, &bearer(next.access_token.as_deref().unwrap()), false).unwrap(),
            authenticate(&app, &bearer(admin.access_token.as_deref().unwrap()), false).unwrap()
        );
    }
    #[test]
    fn password_hash_update_rejects_stale_snapshot_without_overwriting_winner() {
        let db = Connection::open_in_memory().unwrap();
        db.execute_batch(
            "CREATE TABLE accounts (subject TEXT PRIMARY KEY, password_hash TEXT NOT NULL, must_change_password INTEGER NOT NULL);
             INSERT INTO accounts VALUES ('user', 'initial-hash', 1);",
        )
        .unwrap();
        // Both callers verified the same snapshot before preparing their new
        // hashes outside the database lock. Only the first write may succeed.
        replace_password_hash(&db, "user", "initial-hash", "winning-hash", true).unwrap();
        assert_eq!(
            replace_password_hash(&db, "user", "initial-hash", "stale-hash", true),
            Err(INVALID)
        );
        let persisted: String = db
            .query_row(
                "SELECT password_hash FROM accounts WHERE subject='user'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(persisted, "winning-hash");
        // After first rotation, the pending flag stays false across ordinary
        // password changes. Only the exact hash snapshot excludes a stale writer.
        replace_password_hash(&db, "user", "winning-hash", "next-hash", false).unwrap();
        assert_eq!(
            replace_password_hash(&db, "user", "winning-hash", "stale-completed-hash", false),
            Err(INVALID)
        );
        let completed: (String, bool) = db
            .query_row(
                "SELECT password_hash,must_change_password FROM accounts WHERE subject='user'",
                [],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .unwrap();
        assert_eq!(completed, ("next-hash".into(), false));
    }
    #[tokio::test]
    async fn concurrent_first_password_changes_have_one_winner_after_restart() {
        let (dir, app) = fixture();
        let Json(admin) = login(
            State(app.clone()),
            Json(Credentials {
                email: "admin@example.test".into(),
                password: "initial-password-123".into(),
            }),
        )
        .await
        .unwrap();
        let (_, Json(account)) = create_account(
            State(app.clone()),
            bearer(admin.admin_token.as_ref().unwrap()),
            Json(Credentials {
                email: "race@example.test".into(),
                password: "temporary-password-123".into(),
            }),
        )
        .await
        .unwrap();
        let reopened = read_app(
            &dir.path().join("issuer"),
            app.issuer.clone(),
            app.audience.clone(),
        )
        .unwrap();
        let Json(pending) = login(
            State(reopened.clone()),
            Json(Credentials {
                email: "race@example.test".into(),
                password: "temporary-password-123".into(),
            }),
        )
        .await
        .unwrap();
        assert!(pending.must_change_password);
        assert!(pending.access_token.is_none());
        let credential = pending.password_change_token.unwrap();
        let (first, second) = tokio::join!(
            change_password(
                State(app.clone()),
                bearer(&credential),
                Json(PasswordChange {
                    current_password: "temporary-password-123".into(),
                    new_password: "first-chosen-password-123".into(),
                })
            ),
            change_password(
                State(reopened.clone()),
                bearer(&credential),
                Json(PasswordChange {
                    current_password: "temporary-password-123".into(),
                    new_password: "second-chosen-password-123".into(),
                })
            ),
        );
        assert_ne!(first.is_ok(), second.is_ok());
        let winner = if first.is_ok() {
            "first-chosen-password-123"
        } else {
            "second-chosen-password-123"
        };
        let losing_result = if first.is_ok() { second } else { first };
        assert_eq!(losing_result.unwrap_err(), INVALID);
        let restarted = read_app(
            &dir.path().join("issuer"),
            app.issuer.clone(),
            app.audience.clone(),
        )
        .unwrap();
        assert_eq!(
            change_password(
                State(restarted.clone()),
                bearer(&credential),
                Json(PasswordChange {
                    current_password: winner.into(),
                    new_password: "replayed-chosen-password-123".into(),
                })
            )
            .await
            .unwrap_err(),
            INVALID
        );
        let Json(completed) = login(
            State(restarted),
            Json(Credentials {
                email: "race@example.test".into(),
                password: winner.into(),
            }),
        )
        .await
        .unwrap();
        assert!(!completed.must_change_password);
        assert_eq!(
            authenticate(
                &app,
                &bearer(completed.access_token.as_deref().unwrap()),
                false
            )
            .unwrap(),
            account.subject
        );
    }
    #[test]
    fn rotation_credentials_require_exact_audience_purpose_and_expiry() {
        let (_dir, app) = fixture();
        let rotation = token(
            &app,
            "subject",
            TokenKind::PasswordChange,
            "subject@example.test",
        )
        .unwrap();
        assert!(authenticate_kind(&app, &bearer(&rotation), TokenKind::PasswordChange).is_ok());
        assert!(authenticate(&app, &bearer(&rotation), false).is_err());
        assert!(authenticate(&app, &bearer(&rotation), true).is_err());
        let mut validation = Validation::new(Algorithm::RS256);
        validation.set_audience(&[TokenKind::PasswordChange.audience(&app)]);
        let claims = decode::<Claims>(&rotation, &app.decoding, &validation)
            .unwrap()
            .claims;
        for variant in 0..4 {
            let mut altered = Claims {
                ..decode::<Claims>(&rotation, &app.decoding, &validation)
                    .unwrap()
                    .claims
            };
            match variant {
                0 => altered.aud = app.audience.clone(),
                1 => altered.purpose = None,
                2 => altered.purpose = Some("issuer_admin".into()),
                _ => altered.exp = now() - 1,
            }
            let mut header = Header::new(Algorithm::RS256);
            header.kid = Some(app.kid.clone());
            let signed = encode(&header, &altered, &app.encoding).unwrap();
            assert!(authenticate_kind(&app, &bearer(&signed), TokenKind::PasswordChange).is_err());
        }
        assert_eq!(claims.exp - claims.iat, ROTATION_LIFETIME);
        assert!(claims.scope.is_none());
        assert!(claims.subject_kind.is_none());
        let access = token(&app, "subject", TokenKind::Access, "subject@example.test").unwrap();
        let admin = token(&app, "subject", TokenKind::Admin, "subject@example.test").unwrap();
        assert!(authenticate_kind(&app, &bearer(&access), TokenKind::PasswordChange).is_err());
        assert!(authenticate_kind(&app, &bearer(&admin), TokenKind::PasswordChange).is_err());
    }
    #[test]
    fn explicit_upgrade_preserves_retained_identity_and_never_rearms_rotation() {
        let (dir, app) = fixture();
        let path = dir.path().join("issuer");
        let signer = fs::read(path.join("signer.pem")).unwrap();
        {
            let db = app.db.lock().unwrap();
            // Reconstruct exactly the original unversioned account schema.
            db.execute_batch(
                "ALTER TABLE accounts DROP COLUMN must_change_password; PRAGMA user_version=0;",
            )
            .unwrap();
            db.execute(
                "INSERT INTO accounts VALUES ('retained-subject','retained@example.test',?1,0)",
                [&app.dummy_hash],
            )
            .unwrap();
        }
        assert!(read_app(&path, app.issuer.clone(), app.audience.clone()).is_err());
        app.db.lock().unwrap().execute_batch("CREATE TRIGGER fail_upgrade BEFORE UPDATE ON accounts WHEN OLD.is_admin=0 BEGIN SELECT RAISE(ABORT, 'fixture failure'); END;").unwrap();
        assert!(upgrade(&path).is_err());
        {
            let db = app.db.lock().unwrap();
            assert_eq!(
                db.pragma_query_value(None, "user_version", |r| r.get::<_, i64>(0))
                    .unwrap(),
                0
            );
            assert!(db
                .prepare("SELECT must_change_password FROM accounts")
                .is_err());
            db.execute_batch("DROP TRIGGER fail_upgrade;").unwrap();
        }
        upgrade(&path).unwrap();
        let reopened = read_app(&path, app.issuer.clone(), app.audience.clone()).unwrap();
        assert_eq!(fs::read(path.join("signer.pem")).unwrap(), signer);
        let db = reopened.db.lock().unwrap();
        let retained: (String, String, i64) = db.query_row("SELECT subject,password_hash,must_change_password FROM accounts WHERE email='retained@example.test'", [], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?))).unwrap();
        assert_eq!(
            retained,
            ("retained-subject".into(), app.dummy_hash.clone(), 1)
        );
        assert_eq!(
            db.query_row(
                "SELECT must_change_password FROM accounts WHERE is_admin=1",
                [],
                |r| r.get::<_, i64>(0)
            )
            .unwrap(),
            0
        );
        db.execute(
            "UPDATE accounts SET must_change_password=0 WHERE subject='retained-subject'",
            [],
        )
        .unwrap();
        drop(db);
        upgrade(&path).unwrap();
        assert_eq!(
            reopened
                .db
                .lock()
                .unwrap()
                .query_row(
                    "SELECT must_change_password FROM accounts WHERE subject='retained-subject'",
                    [],
                    |r| r.get::<_, i64>(0)
                )
                .unwrap(),
            0
        );
        // A failed ALTER is rolled back with the version and rows unchanged.
        reopened
            .db
            .lock()
            .unwrap()
            .pragma_update(None, "user_version", 0)
            .unwrap();
        assert!(upgrade(&path).is_err());
        assert_eq!(
            reopened
                .db
                .lock()
                .unwrap()
                .pragma_query_value(None, "user_version", |r| r.get::<_, i64>(0))
                .unwrap(),
            0
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
