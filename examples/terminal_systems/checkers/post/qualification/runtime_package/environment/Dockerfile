FROM alpine@sha256:c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e
COPY tools/qualification-status /usr/local/bin/qualification-status
RUN grep -Eq '^Seccomp:[[:space:]]+2$' /proc/self/status && chmod 0555 /usr/local/bin/qualification-status
USER 65532:65532
