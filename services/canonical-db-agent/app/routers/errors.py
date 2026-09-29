"""Map CRUD exceptions to HTTP responses."""

from contextlib import contextmanager

from fastapi import HTTPException, status

from app import crud


@contextmanager
def crud_errors():
    try:
        yield
    except crud.NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except crud.DuplicateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except crud.ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
