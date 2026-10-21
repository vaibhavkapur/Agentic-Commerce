from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..authz import get_membership
from ..db import get_db
from ..models import DocumentVersion, User
from ..storage import build_storage, verify_download

router = APIRouter(tags=["files"])


@router.get("/files/{token}")
def download(token: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Serve a document through a short-lived signed link. The caller must still be a member of the
    organization that owns the document."""
    try:
        organization_id, document_version_id = verify_download(token)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if get_membership(db, organization_id, user.id) is None:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    doc = db.get(DocumentVersion, document_version_id)
    if doc is None or doc.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Document not found")
    data = build_storage().get(doc.storage_key)
    return Response(content=data, media_type=doc.content_type,
                    headers={"Content-Disposition": f'inline; filename="{doc.filename}"'})
