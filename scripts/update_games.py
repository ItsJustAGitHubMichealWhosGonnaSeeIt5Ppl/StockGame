import os

from dotenv import load_dotenv

from stocks import GameLogic


def main():
    load_dotenv()
    DB_NAME = str(os.getenv('DB_NAME'))
    gl = GameLogic(db_name=DB_NAME)
    # Update all games
    gl.update_all()


if __name__ == "__main__":
    main()