warning: in the working copy of 'database.py', LF will be replaced by CRLF the next time Git touches it
[1mdiff --git a/database.py b/database.py[m
[1mindex 9878ec6..2d4d570 100644[m
[1m--- a/database.py[m
[1m+++ b/database.py[m
[36m@@ -146,33 +146,22 @@[m [masync def ensure_user_tables(session, telegram_id: int, business_name: str) -> d[m
         business_name = "Upload Manuale"[m
     [m
     try:[m
[31m-        # Verifica che l'utente esista nella tabella users (necessario per FOREIGN KEY)[m
[31m-        check_user = sql_text("SELECT id FROM users WHERE telegram_id = :telegram_id")[m
[31m-        result_user = await session.execute(check_user, {"telegram_id": telegram_id})[m
[31m-        user_row = result_user.scalar_one_or_none()[m
[31m-        [m
[31m-        if not user_row:[m
[31m-            # Crea utente se non esiste[m
[31m-            logger.warning(f"User {telegram_id} not found in users table, creating...")[m
[31m-            create_user = sql_text("""[m
[31m-                INSERT INTO users (telegram_id, business_name, created_at, updated_at)[m
[31m-                VALUES (:telegram_id, :business_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)[m
[31m-                ON CONFLICT (telegram_id) DO UPDATE SET business_name = :business_name, updated_at = CURRENT_TIMESTAMP[m
[31m-                RETURNING id[m
[31m-            """)[m
[31m-            result_create = await session.execute(create_user, {"telegram_id": telegram_id, "business_name": business_name})[m
[31m-            user_id = result_create.scalar_one()[m
[31m-            logger.info(f"Created user {telegram_id} with id {user_id}")[m
[31m-        else:[m
[31m-            user_id = user_row[m
[31m-            # Aggiorna business_name se diverso[m
[31m-            update_user = sql_text("""[m
[31m-                UPDATE users SET business_name = :business_name, updated_at = CURRENT_TIMESTAMP[m
[31m-                WHERE telegram_id = :telegram_id[m
[31m-            """)[m
[31m-            await session.execute(update_user, {"telegram_id": telegram_id, "business_name": business_name})[m
[32m+[m[32m        # Verifica e crea/aggiorna utente nella tabella users (necessario per FOREIGN KEY)[m
[32m+[m[32m        # Usa UPSERT atomico per evitare race conditions e semplificare la logica[m
[32m+[m[32m        upsert_user = sql_text("""[m
[32m+[m[32m            INSERT INTO users (telegram_id, business_name, created_at, updated_at)[m
[32m+[m[32m            VALUES (:telegram_id, :business_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)[m
[32m+[m[32m            ON CONFLICT (telegram_id)[m[41m [m
[32m+[m[32m            DO UPDATE SET[m[41m [m
[32m+[m[32m                business_name = EXCLUDED.business_name,[m[41m [m
[32m+[m[32m                updated_at = CURRENT_TIMESTAMP[m
[32m+[m[32m            RETURNING id[m
[32m+[m[32m        """)[m
[32m+[m[32m        result_user = await session.execute(upsert_user, {"telegram_id": telegram_id, "business_name": business_name})[m
[32m+[m[32m        user_id = result_user.scalar_one()[m
[32m+[m[32m        logger.info(f"User {telegram_id} ensured with id {user_id}, business_name: {business_name}")[m
         [m
[31m-        # Commit della creazione/aggiornamento utente[m
[32m+[m[32m        # Commit della creazione/aggiornamento utente prima di creare le tabelle[m
         await session.commit()[m
         # Nomi tabelle[m
         table_inventario = get_user_table_name(telegram_id, business_name, "INVENTARIO")[m
