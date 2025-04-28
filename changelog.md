 Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Changelog
- Readme
- _sql_get method for internal use to hopefully reduce redundancy
- add_stock_pick, list_stock_picks methods
- picks columns and custom columns/table option for _reformat_sqlite method
- Docstrings for methods list_users, list_stocks, get_stock, add_stock_price,
- Lots of placeholder methods
- create_game method now returns status
- Discord bot framework


### Fixed
- Data format for get_stock method

### Changed
- join_datetime to datetime_joined in game_participants table (SQLite DB)
- datetime_updated can no longer be null in stock_picks table (SQLite DB)
- username to display_name in add_user method
- get_stock and list_stock_prices methods now use _sql_get()
- Renamed StockGame class to Backend

### Removed
- Misc placeholders and completed todos

## [0.0.0] - Template

### Added

### Fixed

### Changed

### Removed