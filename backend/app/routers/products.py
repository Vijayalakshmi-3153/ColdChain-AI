"""
Product API routes: CRUD for cold-chain products.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[schemas.ProductRead])
def list_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all products."""
    return crud.get_products(db, skip=skip, limit=limit)


@router.get("/{product_id}", response_model=schemas.ProductRead)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Get a single product by id."""
    product = crud.get_product(db, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.post("", response_model=schemas.ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    """Create a new product."""
    return crud.create_product(db, product)


@router.patch("/{product_id}", response_model=schemas.ProductRead)
def update_product(
    product_id: int, product: schemas.ProductUpdate, db: Session = Depends(get_db)
):
    """Partially update a product."""
    db_product = crud.get_product(db, product_id)
    if db_product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return crud.update_product(db, db_product, product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """Delete a product (cascades to its shipments)."""
    db_product = crud.get_product(db, product_id)
    if db_product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    crud.delete_product(db, db_product)