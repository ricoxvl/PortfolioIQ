from __future__ import annotations
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from server.store import Base, DATABASE_URL
config=context.config
if config.config_file_name is not None:fileConfig(config.config_file_name)
config.set_main_option('sqlalchemy.url',DATABASE_URL.replace('%','%%'))
target_metadata=Base.metadata

def offline():
    context.configure(url=DATABASE_URL,target_metadata=target_metadata,literal_binds=True,dialect_opts={'paramstyle':'named'})
    with context.begin_transaction():context.run_migrations()

def online():
    connection=engine_from_config(config.get_section(config.config_ini_section),prefix='sqlalchemy.',poolclass=pool.NullPool).connect()
    try:
        context.configure(connection=connection,target_metadata=target_metadata,compare_type=True)
        with context.begin_transaction():context.run_migrations()
    finally: connection.close()
if context.is_offline_mode():offline()
else:online()
