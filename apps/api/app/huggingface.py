"""Hugging Face repo metadata lookup for the import-hf endpoint (metadata only — the
actual file download happens in the worker, see workers/ops/import_hf.py)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from huggingface_hub import HfApi
from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError
from modelforge_catalog.hf_files import HfRepoFile, select_repo_files, total_bytes

from .config import Settings


class HfRepoNotFoundError(Exception):
    pass


class HfRepoGatedError(Exception):
    pass


class HfUnsupportedRepoError(Exception):
    pass


class HfUnavailableError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class HfRepoEstimate:
    selected_files: list[str]
    total_size_bytes: int


class HuggingFaceService(Protocol):
    def estimate(self, repo_id: str, token: str | None) -> HfRepoEstimate: ...


class HfHubService:
    """Real implementation, backed by huggingface_hub. Never downloads file contents and
    never imports transformers/torch — see root CLAUDE.md on never loading model bytes
    inside the API."""

    def __init__(self, settings: Settings) -> None:
        self._timeout = settings.hf_timeout_seconds

    def estimate(self, repo_id: str, token: str | None) -> HfRepoEstimate:
        api = HfApi()
        try:
            info = api.model_info(
                repo_id, token=token, files_metadata=True, timeout=self._timeout
            )
        except RepositoryNotFoundError as error:
            raise HfRepoNotFoundError(repo_id) from error
        except GatedRepoError as error:
            raise HfRepoGatedError(repo_id) from error
        except Exception as error:  # huggingface_hub raises various HfHubHTTPError subtypes
            raise HfUnavailableError(str(error)) from error

        if getattr(info, "gated", False) and not token:
            raise HfRepoGatedError(repo_id)

        siblings = [
            HfRepoFile(path=s.rfilename, size=s.size or 0) for s in (info.siblings or [])
        ]
        chosen = select_repo_files(siblings)
        if not chosen:
            raise HfUnsupportedRepoError(repo_id)
        return HfRepoEstimate(
            selected_files=[f.path for f in chosen], total_size_bytes=total_bytes(chosen)
        )
