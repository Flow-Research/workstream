FROM rust:1.99.1-bookworm AS build
WORKDIR /src
COPY experiments/demo_identity/Cargo.toml experiments/demo_identity/Cargo.lock ./
COPY experiments/demo_identity/src ./src
RUN cargo build --release --locked

FROM debian:bookworm-slim
RUN useradd --system --uid 12001 --home /nonexistent --shell /usr/sbin/nologin issuer
COPY --from=build /src/target/release/workstream-demo-identity /usr/local/bin/demo-identity
USER 12001:12001
ENTRYPOINT ["/usr/local/bin/demo-identity"]
