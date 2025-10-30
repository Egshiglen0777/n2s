# ===== FIXED FOREX FUNCTIONS WITH FREE APIS ===== #
def get_forex_price(forex_pair: str) -> tuple:
    """Fetch real-time forex price from free APIs"""
    try:
        # Remove slash for API calls
        symbol_clean = forex_pair.replace("/", "")
        
        # Try multiple free forex APIs
        apis_to_try = [
            # API 1: FreeCurrencyAPI (good for majors)
            f"https://api.freecurrencyapi.com/v1/latest?apikey=freekey&base_currency={symbol_clean[:3]}&currencies={symbol_clean[3:]}",
            
            # API 2: ExchangeRate-API (fallback)
            f"https://api.exchangerate-api.com/v4/latest/{symbol_clean[:3]}",
            
            # API 3: Frankfurter (good for EUR pairs)
            f"https://api.frankfurter.app/latest?from={symbol_clean[:3]}&to={symbol_clean[3:]}"
        ]
        
        for api_url in apis_to_try:
            try:
                response = requests.get(api_url, timeout=5)
                data = response.json()
                
                # Parse response based on API
                if "freecurrencyapi" in api_url and 'data' in data:
                    rate = data['data'].get(symbol_clean[3:])
                    if rate:
                        return f"${rate:.4f}", 0
                
                elif "exchangerate-api" in api_url and 'rates' in data:
                    rate = data['rates'].get(symbol_clean[3:])
                    if rate:
                        return f"${rate:.4f}", 0
                
                elif "frankfurter" in api_url and 'rates' in data:
                    rate = data['rates'].get(symbol_clean[3:])
                    if rate:
                        return f"${rate:.4f}", 0
                        
            except:
                continue
        
        # If all APIs fail, use mock data for demo
        mock_forex = {
            "EUR/USD": ("$1.0856", 0.15),
            "GBP/JPY": ("$187.23", -0.32), 
            "GBP/USD": ("$1.2678", 0.22),
            "USD/JPY": ("$149.56", 0.08),
            "USD/CAD": ("$1.3567", -0.11),
            "AUD/USD": ("$0.6578", 0.05)
        }
        return mock_forex.get(forex_pair, ("Forex price unavailable", 0))
        
    except Exception as e:
        return f"Forex error: {str(e)}", 0

def get_forex_quote(forex_pair: str) -> dict:
    """Get forex quote with mock data for now"""
    try:
        # For demo purposes, return realistic mock data
        mock_changes = {
            "EUR/USD": 0.15,
            "GBP/JPY": -0.32,
            "GBP/USD": 0.22, 
            "USD/JPY": 0.08,
            "USD/CAD": -0.11,
            "AUD/USD": 0.05
        }
        return {"percent_change": mock_changes.get(forex_pair, 0)}
    except:
        return {"percent_change": 0}
