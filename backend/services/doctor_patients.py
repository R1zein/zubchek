import logging
from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.doctor_patients import Doctor_patients

logger = logging.getLogger(__name__)


# ------------------ Service Layer ------------------
class Doctor_patientsService:
    """Service layer for Doctor_patients operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Doctor_patients]:
        """Create a new doctor_patients"""
        try:
            if user_id:
                data['user_id'] = user_id
            obj = Doctor_patients(**data)
            self.db.add(obj)
            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Created doctor_patients with id: {obj.id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating doctor_patients: {str(e)}")
            raise

    async def check_ownership(self, obj_id: int, user_id: str) -> bool:
        """Check if user owns this record"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            return obj is not None
        except Exception as e:
            logger.error(f"Error checking ownership for doctor_patients {obj_id}: {str(e)}")
            return False

    async def get_by_id(self, obj_id: int, user_id: Optional[str] = None) -> Optional[Doctor_patients]:
        """Get doctor_patients by ID (user can only see their own records)"""
        try:
            query = select(Doctor_patients).where(Doctor_patients.id == obj_id)
            if user_id:
                query = query.where(Doctor_patients.user_id == user_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching doctor_patients {obj_id}: {str(e)}")
            raise

    async def get_list(
        self, 
        skip: int = 0, 
        limit: int = 20, 
        user_id: Optional[str] = None,
        query_dict: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of doctor_patientss (user can only see their own records)"""
        try:
            query = select(Doctor_patients)
            count_query = select(func.count(Doctor_patients.id))
            
            if user_id:
                query = query.where(Doctor_patients.user_id == user_id)
                count_query = count_query.where(Doctor_patients.user_id == user_id)
            
            if query_dict:
                for field, value in query_dict.items():
                    if hasattr(Doctor_patients, field):
                        query = query.where(getattr(Doctor_patients, field) == value)
                        count_query = count_query.where(getattr(Doctor_patients, field) == value)
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar()

            if sort:
                if sort.startswith('-'):
                    field_name = sort[1:]
                    if hasattr(Doctor_patients, field_name):
                        query = query.order_by(getattr(Doctor_patients, field_name).desc())
                else:
                    if hasattr(Doctor_patients, sort):
                        query = query.order_by(getattr(Doctor_patients, sort))
            else:
                query = query.order_by(Doctor_patients.id.desc())

            result = await self.db.execute(query.offset(skip).limit(limit))
            items = result.scalars().all()

            return {
                "items": items,
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Error fetching doctor_patients list: {str(e)}")
            raise

    async def update(self, obj_id: int, update_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Doctor_patients]:
        """Update doctor_patients (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Doctor_patients {obj_id} not found for update")
                return None
            for key, value in update_data.items():
                if hasattr(obj, key) and key != 'user_id':
                    setattr(obj, key, value)

            await self.db.commit()
            await self.db.refresh(obj)
            logger.info(f"Updated doctor_patients {obj_id}")
            return obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating doctor_patients {obj_id}: {str(e)}")
            raise

    async def delete(self, obj_id: int, user_id: Optional[str] = None) -> bool:
        """Delete doctor_patients (requires ownership)"""
        try:
            obj = await self.get_by_id(obj_id, user_id=user_id)
            if not obj:
                logger.warning(f"Doctor_patients {obj_id} not found for deletion")
                return False
            await self.db.delete(obj)
            await self.db.commit()
            logger.info(f"Deleted doctor_patients {obj_id}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting doctor_patients {obj_id}: {str(e)}")
            raise

    async def get_by_field(self, field_name: str, field_value: Any) -> Optional[Doctor_patients]:
        """Get doctor_patients by any field"""
        try:
            if not hasattr(Doctor_patients, field_name):
                raise ValueError(f"Field {field_name} does not exist on Doctor_patients")
            result = await self.db.execute(
                select(Doctor_patients).where(getattr(Doctor_patients, field_name) == field_value)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching doctor_patients by {field_name}: {str(e)}")
            raise

    async def list_by_field(
        self, field_name: str, field_value: Any, skip: int = 0, limit: int = 20
    ) -> List[Doctor_patients]:
        """Get list of doctor_patientss filtered by field"""
        try:
            if not hasattr(Doctor_patients, field_name):
                raise ValueError(f"Field {field_name} does not exist on Doctor_patients")
            result = await self.db.execute(
                select(Doctor_patients)
                .where(getattr(Doctor_patients, field_name) == field_value)
                .offset(skip)
                .limit(limit)
                .order_by(Doctor_patients.id.desc())
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching doctor_patientss by {field_name}: {str(e)}")
            raise