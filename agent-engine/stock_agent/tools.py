"""
Stock Agent Tools
Uses yfinance for real-time stock data (free, no API key needed)

These functions will be auto-detected by ADK as tools.
ADK uses the function signature and docstring for tool schema generation.
"""

from datetime import datetime

# yfinance will be installed via requirements.txt
import yfinance as yf


def get_stock_price(symbol: str) -> dict:
    """Get current stock price and daily change for a given stock symbol.
    
    Args:
        symbol: Stock ticker symbol (e.g., AAPL, GOOGL, MSFT)
    
    Returns:
        Dictionary with current price, change, and key metrics
    """
    try:
        ticker = yf.Ticker(symbol.upper())
        info = ticker.info
        
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
    """Get stock price history for a given period.
    
    Args:
        symbol: Stock ticker symbol (e.g., AAPL, GOOGL)
        period: Time period - 1d, 5d, 1mo, 3mo, 6mo, 1y (default: 1mo)
    
    Returns:
        Dictionary with price history summary and statistics
    """
    try:
        ticker = yf.Ticker(symbol.upper())
        hist = ticker.history(period=period)
        
        if hist.empty:
            return {"error": f"No data found for {symbol}"}
        
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
            "recent_prices": [round(p, 2) for p in prices[-5:]]
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}


def compare_stocks(symbols: list[str]) -> dict:
    """Compare multiple stocks side by side.
    
    Args:
        symbols: List of stock ticker symbols to compare (e.g., ["AAPL", "GOOGL", "MSFT"])
    
    Returns:
        Dictionary with comparison data sorted by monthly performance
    """
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
    
    # Sort by monthly performance
    results.sort(key=lambda x: x.get("month_change_pct", 0), reverse=True)
    
    return {
        "comparison": results,
        "best_performer": results[0]["symbol"] if results else None,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def get_company_info(symbol: str) -> dict:
    """Get detailed company information including sector, financials, and description.
    
    Args:
        symbol: Stock ticker symbol (e.g., AAPL, AMZN)
    
    Returns:
        Dictionary with company details and financial metrics
    """
    try:
        ticker = yf.Ticker(symbol.upper())
        info = ticker.info
        
        summary = info.get("longBusinessSummary", "")
        if summary and len(summary) > 500:
            summary = summary[:500] + "..."
        
        return {
            "symbol": symbol.upper(),
            "name": info.get("longName", "Unknown"),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "country": info.get("country", "Unknown"),
            "employees": info.get("fullTimeEmployees", 0),
            "website": info.get("website", ""),
            "summary": summary,
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
    """Analyze stock trend using moving averages and volume indicators.
    
    Args:
        symbol: Stock ticker symbol (e.g., NVDA, TSLA)
    
    Returns:
        Dictionary with trend analysis, signals, and basic indicators
    """
    try:
        ticker = yf.Ticker(symbol.upper())
        hist = ticker.history(period="3mo")
        
        if hist.empty:
            return {"error": f"No data for {symbol}"}
        
        prices = hist["Close"].tolist()
        volumes = hist["Volume"].tolist()
        
        # Calculate moving averages
        current = prices[-1]
        sma_20 = sum(prices[-20:]) / min(20, len(prices[-20:]))
        sma_50 = sum(prices[-50:]) / min(50, len(prices[-50:]))
        
        # Determine trend
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
        if recent_volume > avg_volume * 1.2:
            volume_trend = "HIGH"
        elif recent_volume > avg_volume * 0.8:
            volume_trend = "NORMAL"
        else:
            volume_trend = "LOW"
        
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
            "disclaimer": "This is basic technical analysis, not financial advice."
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}
