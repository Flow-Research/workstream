# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
# Keycloak 26.8.2, Linux amd64. Keep upstream and deployed image digests in evidence.
FROM quay.io/keycloak/keycloak@sha256:4da21f9a53bcbac1026a0d654b740a81e98e5de4c45457076acc74b4d94b1551 AS builder
RUN /opt/keycloak/bin/kc.sh build --db=postgres --health-enabled=true --metrics-enabled=true

FROM quay.io/keycloak/keycloak@sha256:4da21f9a53bcbac1026a0d654b740a81e98e5de4c45457076acc74b4d94b1551
COPY --from=builder /opt/keycloak/ /opt/keycloak/
COPY --chmod=0555 deploy/identity/entrypoint.sh /opt/workstream/identity-entrypoint.sh
USER 1000:0
ENTRYPOINT ["/opt/workstream/identity-entrypoint.sh"]
CMD ["start", "--optimized"]
