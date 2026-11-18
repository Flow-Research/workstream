# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
# Keycloak 26.8.2, Linux amd64. Keep upstream and deployed image digests in evidence.
FROM quay.io/keycloak/keycloak@sha256:4da21f9a53bcbac1026a0d654b740a81e98e5de4c45457076acc74b4d94b1551 AS upstream

FROM eclipse-temurin:21-jdk@sha256:db5cc6341a1d7bc40cdb51e1f0d9824f3bb2cc8107d29da421dc4df7d11f05f1 AS provider
COPY --from=upstream /opt/keycloak/lib/lib/main/ /provider-libs/
COPY deploy/identity/provider/ /src/
RUN mkdir /classes && javac --release 21 -cp '/provider-libs/*' -d /classes /src/src/tech/flowresearch/identity/*.java \
    && jar --create --file /flow-registration.jar -C /classes . -C /src/resources .

FROM upstream AS builder
COPY --from=provider /flow-registration.jar /opt/keycloak/providers/flow-registration.jar
RUN /opt/keycloak/bin/kc.sh build --db=postgres --health-enabled=true --metrics-enabled=true

FROM quay.io/keycloak/keycloak@sha256:4da21f9a53bcbac1026a0d654b740a81e98e5de4c45457076acc74b4d94b1551
COPY --from=builder /opt/keycloak/ /opt/keycloak/
COPY deploy/identity/themes/ /opt/keycloak/themes/
COPY --chmod=0555 deploy/identity/entrypoint.sh /opt/workstream/identity-entrypoint.sh
USER 1000:0
ENTRYPOINT ["/opt/workstream/identity-entrypoint.sh"]
CMD ["start", "--optimized"]
