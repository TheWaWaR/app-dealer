

-- Create database
CREATE DATABASE `_testdb` CHARACTER SET utf8 COLLATE utf8_general_ci;
USE _testdb;

-- Create tables
CREATE TABLE test_table(
   id INT NOT NULL AUTO_INCREMENT,
   title VARCHAR(100) NOT NULL,
   author VARCHAR(40) NOT NULL,
   submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
   PRIMARY KEY ( id )
);

-- Insert init records
INSERT INTO test_table(title, author) VALUES('Talk about rust-lang', 'weet');
INSERT INTO test_table(title, author) VALUES('The Future of concurrency', 'thewawar');
