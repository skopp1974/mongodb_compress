// Runs only on first container startup when /data/db is empty.
// Creating a collection ensures the DB is materialized.
db = db.getSiblingDB("compress_poc");
db.createCollection("init");

