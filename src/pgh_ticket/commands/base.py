"""Base class for all pgh-ticket CLI commands."""


class BaseCommand:
    """Base for all commands.

    Subclasses override ``__call__(self, ...)`` with their CLI parameter signature.
    Cyclopts inspects the ``__call__`` signature for argument parsing -- identical to
    how it inspects bare async functions.

    The ``db`` parameter (when present) is injected by the meta app in ``cli.py``
    via ``Parameter(parse=False)``, so subclasses never call ``Database(db_path).init()``.
    """

    pass
