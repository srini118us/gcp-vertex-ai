"""
Lab 03: Stock Agent with Real Market Data
GCP Vertex AI Learning Path

Uses yfinance for real-time stock data (free, no API key needed)
"""

import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Install: pip install yfinance
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("⚠️  yfinance not installed. Run: pip install yfinance")

load_dotenv()

# Configure Gemini API
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL = "gemini-2.5-flash"


# ============================================
# Tool Functions with Real Data
# ============================================

def get_stock_price(symbol: str) -> dict:
    """Get current stock price and daily change."""
    
    if not YFINANCE_AVAILABLE:
        return {"error": "yfinance not installed"}
    
    try:
        ticker = yf.Ticker(symbol.upper())
        info = ticker.info
        
        # Get current price data
        current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        previous_close = info.get("previousClose", 0)
        change = current_price - previous_close if previous_close else 0
        change_pct = (change / previous_close * 100) if previous_close else 0
        
        return {
            "symbol": symbol.upper(),
            "company": info.get("shortName", "Unknown"),
            "current_price": round(current_price, 2),
            "previous_close": round(previous_close, 2),
            "change": round(change, 2),
            "change_percent": round(change_pct, 2),
            "day_high": round(info.get("dayHigh", 0), 2),
            "day_low": round(info.get("dayLow", 0), 2),
            "volume": info.get("volume", 0),
            "market_cap": info.get("marketCap", 0),
            "currency": info.get("currency", "USD"),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}


def get_stock_history(symbol: str, period: str = "1mo") -> dict:
    """Get stock price history.
    
    Args:
        symbol: Stock ticker (e.g., AAPL, GOOGL)
        period: 1d, 5d, 1mo, 3mo, 6mo, 1y
    """
    
    if not YFINANCE_AVAILABLE:
        return {"error": "yfinance not installed"}
    
    try:
        ticker = yf.Ticker(symbol.upper())
        hist = ticker.history(period=period)
        
        if hist.empty:
            return {"error": f"No data found for {symbol}"}
        
        # Get summary stats
        prices = hist["Close"].tolist()
        
        return {
            "symbol": symbol.upper(),
            "period": period,
            "data_points": len(prices),
            "start_price": round(prices[0], 2),
            "end_price": round(prices[-1], 2),
            "high": round(max(prices), 2),
            "low": round(min(prices), 2),
            "average": round(sum(prices) / len(prices), 2),
            "total_change": round(prices[-1] - prices[0], 2),
            "total_change_pct": round((prices[-1] - prices[0]) / prices[0] * 100, 2),
            "recent_prices": [round(p, 2) for p in prices[-5:]]  # Last 5 days
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}


def compare_stocks(symbols: list) -> dict:
    """Compare multiple stocks."""
    
    if not YFINANCE_AVAILABLE:
        return {"error": "yfinance not installed"}
    
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",")]
    
    results = []
    for symbol in symbols[:5]:  # Limit to 5 stocks
        try:
            ticker = yf.Ticker(symbol.upper())
            info = ticker.info
            hist = ticker.history(period="1mo")
            
            if not hist.empty:
                prices = hist["Close"].tolist()
                month_change = ((prices[-1] - prices[0]) / prices[0] * 100) if prices[0] else 0
            else:
                month_change = 0
            
            results.append({
                "symbol": symbol.upper(),
                "company": info.get("shortName", "Unknown"),
                "price": round(info.get("currentPrice") or info.get("regularMarketPrice", 0), 2),
                "pe_ratio": round(info.get("trailingPE", 0), 2),
                "market_cap_b": round(info.get("marketCap", 0) / 1e9, 2),
                "month_change_pct": round(month_change, 2),
                "52w_high": round(info.get("fiftyTwoWeekHigh", 0), 2),
                "52w_low": round(info.get("fiftyTwoWeekLow", 0), 2)
            })
        except Exception as e:
            results.append({"symbol": symbol.upper(), "error": str(e)})
    
    # Sort by month change
    results.sort(key=lambda x: x.get("month_change_pct", 0), reverse=True)
    
    return {
        "comparison": results,
        "best_performer": results[0]["symbol"] if results else None,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def get_company_info(symbol: str) -> dict:
    """Get detailed company information."""
    
    if not YFINANCE_AVAILABLE:
        return {"error": "yfinance not installed"}
    
    try:
        ticker = yf.Ticker(symbol.upper())
        info = ticker.info
        
        return {
            "symbol": symbol.upper(),
            "name": info.get("longName", "Unknown"),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "country": info.get("country", "Unknown"),
            "employees": info.get("fullTimeEmployees", 0),
            "website": info.get("website", ""),
            "summary": info.get("longBusinessSummary", "")[:500] + "..." if info.get("longBusinessSummary") else "",
            "financials": {
                "market_cap": info.get("marketCap", 0),
                "revenue": info.get("totalRevenue", 0),
                "profit_margin": round(info.get("profitMargins", 0) * 100, 2),
                "pe_ratio": round(info.get("trailingPE", 0), 2),
                "dividend_yield": round(info.get("dividendYield", 0) * 100, 2) if info.get("dividendYield") else 0
            }
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}


def analyze_trend(symbol: str) -> dict:
    """Analyze stock trend with basic indicators."""
    
    if not YFINANCE_AVAILABLE:
        return {"error": "yfinance not installed"}
    
    try:
        ticker = yf.Ticker(symbol.upper())
        hist = ticker.history(period="3mo")
        
        if hist.empty:
            return {"error": f"No data for {symbol}"}
        
        prices = hist["Close"].tolist()
        volumes = hist["Volume"].tolist()
        
        # Calculate simple indicators
        current = prices[-1]
        sma_20 = sum(prices[-20:]) / min(20, len(prices[-20:]))
        sma_50 = sum(prices[-50:]) / min(50, len(prices[-50:]))
        
        # Trend determination
        if current > sma_20 > sma_50:
            trend = "BULLISH"
            signal = "Price above both moving averages - upward momentum"
        elif current < sma_20 < sma_50:
            trend = "BEARISH"
            signal = "Price below both moving averages - downward momentum"
        else:
            trend = "NEUTRAL"
            signal = "Mixed signals - consolidation phase"
        
        # Volume analysis
        avg_volume = sum(volumes) / len(volumes)
        recent_volume = sum(volumes[-5:]) / 5
        volume_trend = "HIGH" if recent_volume > avg_volume * 1.2 else "NORMAL" if recent_volume > avg_volume * 0.8 else "LOW"
        
        # Volatility (simple std dev)
        mean_price = sum(prices) / len(prices)
        variance = sum((p - mean_price) ** 2 for p in prices) / len(prices)
        volatility = (variance ** 0.5) / mean_price * 100
        
        return {
            "symbol": symbol.upper(),
            "current_price": round(current, 2),
            "sma_20": round(sma_20, 2),
            "sma_50": round(sma_50, 2),
            "trend": trend,
            "signal": signal,
            "volume_trend": volume_trend,
            "volatility_pct": round(volatility, 2),
            "analysis_date": datetime.now().strftime("%Y-%m-%d"),
            "disclaimer": "This is basic analysis, not financial advice."
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}


# ============================================
# Tool Declarations
# ============================================

tool_declarations = [
    {
        "name": "get_stock_price",
        "description": "Get current stock price, daily change, and key metrics",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker symbol (e.g., AAPL, GOOGL, MSFT)"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_stock_history",
        "description": "Get stock price history for a given period",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker symbol"},
                "period": {"type": "string", "description": "Time period: 1d, 5d, 1mo, 3mo, 6mo, 1y (default: 1mo)"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "compare_stocks",
        "description": "Compare multiple stocks side by side",
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of stock symbols to compare (e.g., ['AAPL', 'GOOGL', 'MSFT'])"
                }
            },
            "required": ["symbols"]
        }
    },
    {
        "name": "get_company_info",
        "description": "Get detailed company information including sector, financials, and description",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker symbol"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "analyze_trend",
        "description": "Analyze stock trend using moving averages and volume",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock ticker symbol"}
            },
            "required": ["symbol"]
        }
    }
]

function_map = {
    "get_stock_price": get_stock_price,
    "get_stock_history": get_stock_history,
    "compare_stocks": compare_stocks,
    "get_company_info": get_company_info,
    "analyze_trend": analyze_trend
}


# ============================================
# Agent Runner
# ============================================

def run_agent(user_query: str):
    """Run the Stock Agent."""
    
    print(f"\n{'='*60}")
    print(f"User Query: {user_query}")
    print('='*60)
    
    system_instruction = """You are a helpful stock market analyst assistant.
    You provide real-time stock data and analysis using available tools.
    Be concise but informative. Always mention that this is not financial advice.
    Format numbers clearly (use $ for prices, % for percentages).
    When comparing stocks, present data in a clear tabular format."""
    
    tools = [types.Tool(function_declarations=tool_declarations)]
    
    response = client.models.generate_content(
        model=MODEL,
        contents=user_query,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            temperature=0.1
        )
    )
    
    candidate = response.candidates[0]
    part = candidate.content.parts[0]
    
    if hasattr(part, 'function_call') and part.function_call:
        function_call = part.function_call
        function_name = function_call.name
        function_args = dict(function_call.args) if function_call.args else {}
        
        print(f"\n🔧 Agent calling tool: {function_name}")
        print(f"   Arguments: {function_args}")
        
        if function_name in function_map:
            # Set defaults
            if function_name == "get_stock_history" and "period" not in function_args:
                function_args["period"] = "1mo"
            
            result = function_map[function_name](**function_args)
            print(f"   Result: {json.dumps(result, indent=2)}")
            
            # Build conversation with function result
            contents = [
                types.Content(role="user", parts=[types.Part.from_text(text=user_query)]),
                types.Content(role="model", parts=[types.Part.from_function_call(name=function_name, args=function_args)]),
                types.Content(role="user", parts=[types.Part.from_function_response(name=function_name, response=result)])
            ]
            
            final_response = client.models.generate_content(
                model=MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=tools,
                    temperature=0.1
                )
            )
            
            print(f"\n📋 Agent Response:")
            print(final_response.text)
        else:
            print(f"Unknown function: {function_name}")
    else:
        print(f"\n📋 Agent Response:")
        print(response.text)


# ============================================
# Main
# ============================================

if __name__ == "__main__":
    print("="*60)
    print("📈 Stock Market Agent")
    print("   Real-time data from Yahoo Finance")
    print("="*60)
    
    if not YFINANCE_AVAILABLE:
        print("\n⚠️  Install yfinance: pip install yfinance")
        exit(1)
    
    print("\n📝 Example queries:")
    print("   1. What's the current price of Apple?")
    print("   2. Compare AAPL, GOOGL, and MSFT")
    print("   3. Show me Tesla's stock history for the past month")
    print("   4. Analyze the trend for NVDA")
    print("   5. Tell me about Amazon as a company")
    print("\n   Type 'quit' to exit\n")
    
    while True:
        user_input = input("You: ").strip()
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        if not user_input:
            continue
            
        run_agent(user_input)
