import json
from binance.client import Client

def get_filtered_symbols_test(client, quote_asset, trd_grp_to_test=None):
    """
    Fetches symbols from Binance and filters them by quote asset,
    excluding leveraged tokens, and optionally by a specific TRD_GRP.
    """
    try:
        all_symbols_info = client.get_exchange_info()['symbols']
        
        filtered_pairs = [
            s['symbol'] for s in all_symbols_info
            if (s['quoteAsset'] == quote_asset)
            and 'UP' not in s['symbol']
            and 'DOWN' not in s['symbol']
            and 'BEAR' not in s['symbol']
            and 'BULL' not in s['symbol']
            and (trd_grp_to_test is None or trd_grp_to_test in s.get('permissions', []))
        ]
        return filtered_pairs
    except Exception as e:
        print(f"Error in get_filtered_symbols_test: {e}. Returning empty list.")
        return []

if __name__ == "__main__":
    try:
        with open('credentials_b.json') as f:
            credentials = json.load(f)
        api_key = credentials['Binance_api_key']
        api_secret = credentials['Binance_secret_key']
        client = Client(api_key, api_secret)

        print("\n--- Account Info ---")
        account_info = client.get_account()
        print(json.dumps(account_info, indent=2))
        print("--------------------\n")

        account_permissions = account_info.get('permissions', [])
        trd_grps_found = [p for p in account_permissions if p.startswith('TRD_GRP_')]
        
        print("\n--- Testing with Account Permissions ---")
        if "SPOT" in account_permissions:
            print("Account has 'SPOT' permission. Testing filtering with 'SPOT'.")
            usdc_pairs_spot = get_filtered_symbols_test(client, 'USDC', trd_grp_to_test='SPOT')
            print(f"USDC Pairs (SPOT) ({len(usdc_pairs_spot)}):")
            print(usdc_pairs_spot)
            btc_pairs_spot = get_filtered_symbols_test(client, 'BTC', trd_grp_to_test='SPOT')
            print(f"BTC Pairs (SPOT) ({len(btc_pairs_spot)}):")
            print(btc_pairs_spot)
        else:
            print("Account does NOT have 'SPOT' permission.")

        if trd_grps_found:
            print("\nAccount has TRD_GRP permissions. Testing each found TRD_GRP:")
            for trd_grp in trd_grps_found:
                print(f"\nTesting TRD_GRP: {trd_grp}")
                usdc_pairs_trd = get_filtered_symbols_test(client, 'USDC', trd_grp_to_test=trd_grp)
                print(f"USDC Pairs ({trd_grp}) ({len(usdc_pairs_trd)}):")
                print(usdc_pairs_trd)
                btc_pairs_trd = get_filtered_symbols_test(client, 'BTC', trd_grp_to_test=trd_grp)
                print(f"BTC Pairs ({trd_grp}) ({len(btc_pairs_trd)}):")
                print(btc_pairs_trd)
        else:
            print("\nNo TRD_GRP permissions found in account.")

        print("\n--- Generating Binance Trade URLs for a few examples (unfiltered) ---")
        # Example symbols from the user's alert
        example_symbols = ['BATUSDC', 'MATICBTC']
        
        # Re-using the generate_binance_trade_url logic from b_volume_alerts.py
        def generate_binance_trade_url(symbol):
            if symbol.endswith('USDC'):
                base_asset = symbol[:-4]
                return f"https://www.binance.com/en/trade/{base_asset}_USDC"
            elif symbol.endswith('BTC'):
                base_asset = symbol[:-3]
                return f"https://www.binance.com/en/trade/{base_asset}_BTC"
            return f"https://www.binance.com/en/trade/{symbol}"

        for symbol in example_symbols:
            url = generate_binance_trade_url(symbol)
            print(f"Binance Trade URL for {symbol}: {url}")

    except FileNotFoundError:
        print("Error: credentials_b.json not found. Please ensure it exists and contains your Binance API keys.")
    except json.JSONDecodeError:
        print("Error: Could not decode credentials_b.json. Please check its format.")
    except Exception as e:
        print(f"An error occurred: {e}")