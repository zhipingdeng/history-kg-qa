#!/bin/sh
set -e

echo "==> Creating MySQL tables..."
python -c "
from app.config import get_settings
from app.database.mysql import get_engine, Base
from app.models.user import User
s = get_settings()
engine = get_engine(host=s.mysql_host, port=s.mysql_port, user=s.mysql_user, password=s.mysql_password, database=s.mysql_database)
Base.metadata.create_all(bind=engine)
print('  Tables created.')
"

# Skip auto index build (run manually: python scripts/build_index.py)
# Milvus index is pre-built or built externally

echo "==> Starting server..."
exec "$@"
