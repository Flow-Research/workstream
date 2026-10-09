"""Guide declaration through the real public API and existing bootstrap journey."""

import json
from uuid import uuid4


async def exercise_guide_creation(
    direct, cli, origin, tokens, profiles, project_id, tmp_path
):
    specification = (await direct.get("/openapi.json", timeout=60)).json()
    assert "post" in specification["paths"]["/api/v1/projects/{project_id}/guides"]
    assert (
        "get"
        in specification["paths"][
            "/api/v1/projects/{project_id}/guides/{guide_id}/setup-runs/latest"
        ]
    )
    actor = profiles["cli-project-manager"]["actor_profile_id"]
    token = tokens["cli-project-manager"]
    admin = {"Authorization": f"Bearer {tokens['cli-admin']}"}
    manager = {"Authorization": f"Bearer {tokens['cli-manager']}"}
    caller = {"Authorization": f"Bearer {token}"}
    path = tmp_path / "guide-declaration.json"
    body = {
        "version": "cli-guide-" + uuid4().hex,
        "change_summary": "First source declaration é",
        "task_examples": [
            {"content": "Review the experiment results é\n", "title": None},
            {"content": "Replicate the reported calculation", "labels": ["analysis"]},
        ],
        "documents": [
            {
                "label": "  Study\u0085\u00a0guide.pdf\u001e ",
                "media_type": "application/pdf",
            },
            {
                "label": "Examples.docx",
                "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            },
        ],
    }

    def create(fields, key, project=project_id, presented=token):
        path.write_text(
            json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return cli(
            origin,
            presented,
            "-o",
            "json",
            "project",
            "guide",
            "create",
            project,
            "--input",
            str(path),
            "--idempotency-key",
            key,
        )

    def positive(result):
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)

    def denial(result, statuses=(403, 404), code=None):
        assert result.returncode == 1 and result.stdout == "", result.stderr
        error = json.loads(result.stderr)["error"]
        assert error["status"] in statuses and "outcome_unknown" not in error
        if code:
            assert error["code"] == code

    async def grant():
        response = await direct.post(
            "/api/v1/admin-role-grants",
            headers=admin | {"Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": actor,
                "role": "project_manager",
                "scope_type": "project",
                "scope_project_id": project_id,
                "reason": "CLI guide declaration scoped authority proof",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["resource_id"]

    async def revoke(grant_id):
        response = await direct.post(
            f"/api/v1/admin-role-grants/{grant_id}/revoke",
            headers=admin | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Restore CLI guide fixture"},
        )
        assert response.status_code == 200, response.text

    async def lifecycle(transition):
        response = await direct.post(
            f"/api/v1/actors/{actor}/{transition}",
            headers=admin | {"Idempotency-Key": str(uuid4())},
            json={"reason": "CLI guide lifecycle proof"},
        )
        assert response.status_code == 200, response.text

    for presented in (token, tokens["cli-outsider"], tokens["cli-admin"]):
        denial(create(body, str(uuid4()), presented=presented))
    grant_id = await grant()
    key = str(uuid4())
    created = positive(create(body, key.replace("-", ""), project_id.replace("-", "")))
    assert created["project_id"] == project_id and created["version"] == body["version"]
    assert (
        created["status"] == "draft"
        and created["change_summary"] == body["change_summary"]
    )
    assert created["created_by"] == actor
    assert created["setup"]["status"] == "awaiting_documents"
    assert len({item["document_id"] for item in created["documents"]}) == 2
    assert [
        (item["label"], item["media_type"], item["order"])
        for item in created["documents"]
    ] == [
        (" ".join(item["label"].split()), item["media_type"], index)
        for index, item in enumerate(body["documents"])
    ]
    assert created["task_examples"] == [
        {"title": None, "labels": [], **example} for example in body["task_examples"]
    ]

    # Stored public setup facts and direct replay prove server custody; HTTP
    # fixtures alone cannot prove guide/source/identity persistence.
    root = f"/api/v1/projects/{project_id}/guides/{created['id']}"
    setup = await direct.get(root + "/setup-runs/latest", headers=caller)
    assert setup.status_code == 200, setup.text
    assert setup.json()["id"] == created["setup"]["id"]
    assert setup.json()["status"] == "awaiting_documents"
    assert (
        setup.json()["project_id"] == project_id
        and setup.json()["guide_id"] == created["id"]
    )

    def inspect_setup(*, project=project_id, presented=token):
        return cli(
            origin,
            presented,
            "-o",
            "json",
            "project",
            "guide",
            "setup",
            project,
            created["id"],
        )

    assert positive(inspect_setup()) == setup.json()
    denial(inspect_setup(presented=tokens["cli-outsider"]))
    recovered = await direct.post(
        f"/api/v1/projects/{project_id}/guides",
        headers=caller | {"Idempotency-Key": key},
        json=body,
    )
    assert recovered.status_code == 201 and recovered.json() == created, recovered.text
    assert positive(create(body, key)) == created
    denial(
        create(body | {"change_summary": "Different"}, key),
        (409,),
        "idempotency_mismatch",
    )
    denial(create(body, str(uuid4())), (409,))

    foreign = await direct.post(
        "/api/v1/projects",
        headers=manager | {"Idempotency-Key": str(uuid4())},
        json={"name": "Foreign guide target", "slug": "foreign-guide-" + uuid4().hex},
    )
    assert foreign.status_code == 201, foreign.text
    denial(create(body, str(uuid4()), foreign.json()["id"]))
    denial(inspect_setup(project=foreign.json()["id"]))
    collision = body | {
        "version": "collision-" + uuid4().hex,
        "documents": [
            {"label": "Same.pdf", "media_type": "application/pdf"},
            {"label": "  Same.pdf\u00a0", "media_type": "application/pdf"},
        ],
    }
    denial(create(collision, str(uuid4())), (422,))

    # A positive immediately before revocation discriminates a real authority
    # change from a never-authorized caller. Guide replay rechecks authority.
    positive(create(body | {"version": "before-revoke-" + uuid4().hex}, str(uuid4())))
    assert positive(inspect_setup()) == setup.json()
    await revoke(grant_id)
    denial(inspect_setup())
    denial(create(body, key))
    denial(create(body | {"version": "revoked-" + uuid4().hex}, str(uuid4())))
    grant_id = await grant()
    positive(create(body | {"version": "before-suspend-" + uuid4().hex}, str(uuid4())))
    assert positive(inspect_setup()) == setup.json()
    await lifecycle("suspend")
    denial(inspect_setup())
    denial(create(body, key))
    denial(create(body | {"version": "suspended-" + uuid4().hex}, str(uuid4())))
    await lifecycle("reactivate")
    await revoke(grant_id)
