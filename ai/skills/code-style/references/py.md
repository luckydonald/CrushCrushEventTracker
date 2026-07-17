# Python style

## Visibility and organization

- Do not prefix ordinary identifiers with `_` to express that they are private.
- Do not create private classes or functions. This codebase does not use underscore naming to express private APIs.
- Separate implementation into appropriately scoped modules when that improves organization.
- Python-defined special names such as `__init__`, `__enter__`, and `__all__` are exempt.

## Backend stack

- Target modern Python `3.14+`.
- Fully type-annotate code.
- Prefer the native generic types over `typing.*` aliases (e.g. `dict[str, int]` over `typing.Dict[AnyStr, int]`).
- Prefer async code where practical.
- Web framework: `FastAPI`.
- Database: typed `sqlalchemy` models for Postgres; `alembic` for migrations.

## Testing

- Write tests for the backend code.

## Explicit block endings

End every logical indentation block opened by one of the following statements with a comment aligned with that statement:

- `if` / `elif` / `else` → `# end if`
- `with` / `async with` → `# end with`
- `for` / `async for` → `# end for`
- `while` → `# end while`
- `def` / `async def` → `# end def`
- `class` → `# end class`

Use only the block type in the comment. Do not repeat a function or class name. Close an entire `if` / `elif` / `else` chain with one `# end if`.

```python
class Worker:
    async def run(self) -> None:
        if self.is_ready:
            async with self.connection() as connection:
                await connection.process()
            # end with
        # end if
    # end def
# end class
```
