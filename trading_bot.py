    updated_trades = []
    for index, row in trades_df.iterrows():
        symbol = row['Symbol']
        entry_price = row['Entry']
        tp1 = row['TP1']
        tp2 = row['TP2']
        sl = row['SL']
        qty = row['Qty']
        
        if symbol in current_prices:
            curr_price = current_prices[symbol]
            
            # نظام وقف الخسارة المتحرك (Trailing Stop) للبوت الصارم
            if curr_price >= (entry_price + (tp1 - entry_price) * 0.5) and sl < entry_price:
                sl = entry_price
                row['SL'] = sl
                send_telegram_message(f"🔄 *Strict Trailing Stop Activated! ({symbol})*\nStop Loss moved to Entry Price: `{sl:.3f}`")

            if curr_price >= tp1:
                profit = (tp1 - entry_price) * qty
                current_balance += profit
                msg = f"🎯 *Strict TP Reached! ({symbol})*\nProfit: `+${profit:.2f}`\nBalance: `${current_balance:.2f}`"
                send_telegram_message(msg)
