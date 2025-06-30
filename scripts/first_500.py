# Script to pull all stocks of the S&P 500 and preload them into the database
from dotenv import load_dotenv
import pandas as pd
import requests
from bs4 import BeautifulSoup
import yfinance as yf
from io import StringIO
import sys
import os

current_script_dir = os.path.dirname(os.path.abspath(__file__))

project_root_dir = os.path.dirname(current_script_dir)

sys.path.append(project_root_dir)

from helpers.sqlhelper import _iso8601
from stocks import Backend

load_dotenv()
DB_NAME = str(os.getenv('DB_NAME'))
be = Backend(db_name=DB_NAME)

def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    table = soup.find('table', {'id': 'constituents'})

    if table == None:
        raise ValueError("Could not find the S&P 500 constituents table on the Wikipedia page.")

    df = pd.read_html(StringIO(str(table)))[0] # create Dataframe

    # Extract the 'Symbol' column
    tickers = df['Symbol'].tolist()

    # Clean up any potential anomalies (e.g., some tickers might have a '.' that yfinance doesn't like)
    tickers = [ticker.replace('.', '-') for ticker in tickers]

    return tickers

def get_sp500_info(lst: list):
    ticker_info = yf.Tickers(lst)
    return ticker_info.tickers

def insert_into_db(ticker_dict: dict):
    for key, val in ticker_dict.items():
        info = val.info
        fast_info = val.fast_info
        try:
            be.add_stock(ticker=key.upper(),
                        exchange=info['fullExchangeName'], #TODO this fails with CLR stock
                        company_name=info['displayName'] if 'displayName' in info else info['shortName'])
            
            be.add_stock_price(ticker_or_id=key.upper(),
                               price=fast_info['last_price'] if 'last_price' in fast_info else fast_info['regular_market_previous_close'],
                               datetime=_iso8601())
            
            print(f"Successfully added {key} to the db")
        except:
            print("There was an error")
        # print(f"{key}, exch {info['fullExchangeName']}, name {info['displayName'] if 'displayName' in info else info['shortName']}, price {fast_info['last_price'] if 'last_price' in fast_info else fast_info['regular_market_previous_close']}")

if __name__ == "__main__":
    ticker_list = get_sp500_tickers()
    tickers_dict = get_sp500_info(lst=ticker_list)
    insert_into_db(ticker_dict=tickers_dict)

