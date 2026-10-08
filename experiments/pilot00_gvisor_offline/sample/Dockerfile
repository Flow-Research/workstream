FROM alpine@sha256:c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e

COPY payload.txt /opt/workstream-pilot00/payload.txt
RUN sha256sum /opt/workstream-pilot00/payload.txt \
    > /opt/workstream-pilot00/payload.sha256

USER 65532:65532
ENTRYPOINT ["/bin/sh"]
