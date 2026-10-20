import psycopg2
from psycopg2.extras import Json, execute_values

DB_CONFIG = {
    "dbname": "kaleici_pricing",
    "user": "postgres",
    "password": "your_password",
    "host": "localhost",
    "port": "5432"
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS hotels (
    hotel_id SERIAL PRIMARY KEY,
    booking_slug VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    micro_zone VARCHAR(50) DEFAULT 'Kaleici',
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    review_score DECIMAL(3,1),
    review_count INT,
    star_rating DECIMAL(2,1),
    has_pool BOOLEAN DEFAULT FALSE,
    has_parking BOOLEAN DEFAULT FALSE,
    amenities JSONB DEFAULT '{}'::jsonb,
    url TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS room_types (
    room_id SERIAL PRIMARY KEY,
    hotel_id INT REFERENCES hotels(hotel_id) ON DELETE CASCADE,
    raw_room_name VARCHAR(255) NOT NULL,
    room_tier VARCHAR(50) NOT NULL,
    room_size_sqm INT,
    has_sea_view BOOLEAN DEFAULT FALSE,
    has_balcony BOOLEAN DEFAULT FALSE,
    has_ac BOOLEAN DEFAULT TRUE,
    is_entire_place BOOLEAN DEFAULT FALSE,
    max_adults INT DEFAULT 2,
    UNIQUE(hotel_id, raw_room_name)
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    snapshot_id BIGSERIAL PRIMARY KEY,
    room_id INT REFERENCES room_types(room_id) ON DELETE CASCADE,
    scraped_at TIMESTAMP NOT NULL DEFAULT NOW(),
    check_in_date DATE NOT NULL,
    lead_time_days INT NOT NULL,
    board_type VARCHAR(20) NOT NULL,
    is_refundable BOOLEAN NOT NULL,
    price_eur DECIMAL(10,2),
    rooms_left INT,
    is_sold_out BOOLEAN DEFAULT FALSE
);
"""

MIGRATION_SQL = """
ALTER TABLE hotels ADD COLUMN IF NOT EXISTS star_rating DECIMAL(2,1);
ALTER TABLE room_types ADD COLUMN IF NOT EXISTS room_size_sqm INT;
ALTER TABLE room_types ADD COLUMN IF NOT EXISTS has_balcony BOOLEAN DEFAULT FALSE;
ALTER TABLE room_types ADD COLUMN IF NOT EXISTS has_ac BOOLEAN DEFAULT TRUE;
ALTER TABLE room_types ADD COLUMN IF NOT EXISTS is_entire_place BOOLEAN DEFAULT FALSE;
"""

def init_db():
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(MIGRATION_SQL)
        conn.commit()

if __name__ == "__main__":
    init_db()
    print("Database schema initialized and migrated successfully.")