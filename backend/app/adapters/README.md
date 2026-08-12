# Adapters

Adapters implement interfaces for concrete providers such as Flow auth, local storage, object storage, and checker runners.

Each exact `backend/app/adapters/<owner>/__init__.py` is an owner composition
root. It may import that owner's private implementation only to construct typed
public ports. Nested adapter files must consume module public APIs, and no
adapter may import another module's private implementation.
