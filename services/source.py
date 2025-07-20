# ⚠️ AUTO-GENERATED — DO NOT EDIT
# Generated from: ../public/source.yaml
# Service: source

from typing import Dict
from fastapi import APIRouter, Depends, HTTPException

# Import schemas - these should already exist
from src.schemas.source import Source, SourcesResponse
# Import service layer - this should be created manually in src/services/
from src.services.source_service import SourceService, get_source_service

router = APIRouter()


@router.get("/organizations/{organization_id}/sources", response_model=SourcesResponse)
def list_sources(    organization_id: str,    service: SourceService = Depends(get_source_service),
) -> SourcesResponse:
    """List all sources in an organization"""
    return service.list_sources(organization_id)

@router.post("/organizations/{organization_id}/sources", response_model=Source, status_code=201)
def create_source(    organization_id: str,    source_data: Source,    service: SourceService = Depends(get_source_service),
) -> Source:
    """Create a new source in an organization"""
    try:
        return service.create_source(organization_id, source_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/organizations/{organization_id}/sources/{source_id}", response_model=Source)
def get_source(    organization_id: str,    source_id: str,    service: SourceService = Depends(get_source_service),
) -> Source:
    """Get a specific source in an organization"""
    result = service.get_source(organization_id, source_id)
    if not result:
        raise HTTPException(status_code=404, detail="Source not found")
    return result

@router.put("/organizations/{organization_id}/sources/{source_id}", response_model=Source)
def update_source(    organization_id: str,    source_id: str,    source_data: Source,    service: SourceService = Depends(get_source_service),
) -> Source:
    """Update a source in an organization"""
    if source_data.id != source_id:
        raise HTTPException(status_code=400, detail="ID in body must match path parameter")
    result = service.update_source(organization_id, source_id, source_data)
    if not result:
        raise HTTPException(status_code=404, detail="Source not found")
    return result

@router.delete("/organizations/{organization_id}/sources/{source_id}", status_code=204)
def delete_source(    organization_id: str,    source_id: str,    service: SourceService = Depends(get_source_service),
) -> None:
    """Delete a source in an organization"""
    success = service.delete_source(organization_id, source_id)
    if not success:
        raise HTTPException(status_code=404, detail="Source not found")



@router.get("/health")
def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "source-service"}
