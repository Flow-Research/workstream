# Chunk Contract: WS-ARCH-001-CP06 — ContributionPolicy Validation Port

Disposition: Complete. Risk: L1.

The [implemented bounded contract](../../WS-ARCH-001-CP06.md) replaces this
former non-executable skeleton. CON exposes one caller-session exact-version
validation port with distinct guide-activation and revision-adoption purposes.
It follows existing project-first lock ordering and refreshes locked graph/unit
rows. New binding requires exact current published selector equality; controlled
revision checks the supplied guide-bound historically published version without
reselection. Graph and resource validation is shared with publication.

This port is not guide/attempt custody or authorization. CP07 owns hidden guide
binding and prevents revision-purpose misuse for new activation. AUTH-12H owns
activation authority. TASK/REV later own complete revision context and atomic
attempt rebase. No downstream runtime success is claimed by CP06 tests.
