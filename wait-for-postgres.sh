#!/bin/sh
# Wait for PostgreSQL to be ready
until pg_isready -h postgres -p 5432 -U assistant; do
  echo "Waiting for PostgreSQL..."
  sleep 1
done
echo "PostgreSQL is ready"