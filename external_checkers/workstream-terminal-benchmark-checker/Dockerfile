FROM rust:1.84-bookworm@sha256:479476fa1dec14dfa9ed2dbcaa94cda5ab945e125d45c2d153267cc0135f3b69 AS build
WORKDIR /source
COPY Cargo.toml Cargo.lock ./
COPY workstream-checker-sdk ./workstream-checker-sdk
COPY workstream-checker-service ./workstream-checker-service
COPY workstream-terminal-benchmark-checker ./workstream-terminal-benchmark-checker
RUN cargo build --locked --release --package workstream-terminal-benchmark-checker

FROM gcr.io/distroless/cc-debian12:nonroot@sha256:777e96cf322c46bc32aca926c263624c4dc8d7cf37e2fa65ba2c7e697318ebbb
COPY --from=build /source/target/release/workstream-terminal-benchmark-checker /checker
ENTRYPOINT ["/checker"]
