-- schema.sql : creates the empty database structure. Safe to run many times.
-- Requires MySQL 8.0.16+ (CHECK constraints are enforced from that version).
-- Keep comments on their own lines (init_db.py ignores full-line comments only).

CREATE DATABASE IF NOT EXISTS electricity_db;
USE electricity_db;

CREATE TABLE IF NOT EXISTS consumers (
    consumer_id   INT AUTO_INCREMENT PRIMARY KEY,
    consumer_code VARCHAR(20) NOT NULL UNIQUE,
    consumer_type ENUM('Residential','Commercial','Industrial') NOT NULL,
    region        VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS meters (
    meter_id    INT AUTO_INCREMENT PRIMARY KEY,
    consumer_id INT NOT NULL,
    meter_code  VARCHAR(20) NOT NULL UNIQUE,
    CONSTRAINT fk_meters_consumer
        FOREIGN KEY (consumer_id) REFERENCES consumers(consumer_id)
);

CREATE TABLE IF NOT EXISTS meter_readings (
    reading_id     INT AUTO_INCREMENT PRIMARY KEY,
    meter_id       INT NOT NULL,
    reading_date   DATE NOT NULL,
    cumulative_kwh DECIMAL(12,2) NOT NULL,
    CONSTRAINT fk_readings_meter
        FOREIGN KEY (meter_id) REFERENCES meters(meter_id),
    CONSTRAINT uq_meter_date UNIQUE (meter_id, reading_date),
    CONSTRAINT chk_kwh_nonnegative CHECK (cumulative_kwh >= 0)
);