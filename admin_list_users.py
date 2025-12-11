"""
Script admin per listare utenti nel database.

Uso:
    python admin_list_users.py [--search "nome"]
    
Esempio:
    python admin_list_users.py
    python admin_list_users.py --search "Ristorante"
"""
import asyncio
import logging
import sys
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal, User
from core.logger import setup_colored_logging

# Setup logging
setup_colored_logging("admin_list")
logger = logging.getLogger(__name__)


async def list_users(search_term: Optional[str] = None):
    """
    Lista utenti nel database.
    
    Args:
        search_term: Termine di ricerca (cerca in business_name, username, first_name)
    """
    async with AsyncSessionLocal() as session:
        try:
            # Costruisci query
            stmt = select(User).order_by(User.created_at.desc())
            
            if search_term:
                search_pattern = f"%{search_term}%"
                stmt = stmt.where(
                    or_(
                        User.business_name.ilike(search_pattern),
                        User.username.ilike(search_pattern),
                        User.first_name.ilike(search_pattern),
                        User.last_name.ilike(search_pattern)
                    )
                )
            
            result = await session.execute(stmt)
            users = result.scalars().all()
            
            if not users:
                print("\n❌ Nessun utente trovato")
                if search_term:
                    print(f"   (ricerca: '{search_term}')")
                return
            
            print("\n" + "=" * 80)
            print(f"{'TELEGRAM ID':<15} {'BUSINESS NAME':<30} {'USERNAME':<20} {'NOME':<20}")
            print("=" * 80)
            
            for user in users:
                telegram_id = str(user.telegram_id) if user.telegram_id else "N/A"
                business_name = (user.business_name or "N/A")[:28]
                username = (user.username or "N/A")[:18]
                full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()[:18] or "N/A"
                
                print(f"{telegram_id:<15} {business_name:<30} {username:<20} {full_name:<20}")
            
            print("=" * 80)
            print(f"\n✅ Trovati {len(users)} utenti")
            
            if search_term:
                print(f"   (ricerca: '{search_term}')")
            
        except Exception as e:
            logger.error(f"Errore durante ricerca utenti: {e}", exc_info=True)
            print(f"\n❌ Errore: {e}")
            raise


async def main():
    """Main entry point."""
    search_term = None
    
    if "--search" in sys.argv:
        idx = sys.argv.index("--search")
        if idx + 1 < len(sys.argv):
            search_term = sys.argv[idx + 1]
        else:
            print("❌ Errore: --search richiede un termine di ricerca")
            print("\nUso:")
            print("  python admin_list_users.py [--search \"termine\"]")
            sys.exit(1)
    
    try:
        await list_users(search_term)
        
    except Exception as e:
        logger.error(f"Errore generico: {e}", exc_info=True)
        print(f"\n❌ Errore: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

