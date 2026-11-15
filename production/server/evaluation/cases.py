"""Hand-authored question sets plus synthetic fixtures. No brokerage or live market claims."""
QUESTIONS_DEMO=[('performance_available','Explain my portfolio return'),('performance_available','How did the portfolio perform?'),
 ('risk_available','Explain portfolio volatility'),('risk_available','What is the current risk?'),
 ('xray','Is my ETF portfolio overlapping?'),('xray','Analyze my constituent exposure'),
 ('overview','What holdings do I own?'),('overview','Summarize my portfolio'),
 ('performance_available','Compare the return'),('risk_available','Discuss risk and drawdown'),
 ('xray','Which ETFs overlap?'),('overview','Help me understand this account')]
QUESTIONS_IMPORTED=[('performance_unavailable','Explain portfolio return'),('performance_unavailable','How has it performed?'),
 ('risk_unavailable','What is the annualized volatility?'),('risk_unavailable','Calculate my drawdown and risk'),
 ('xray','Do my ETFs overlap?'),('xray','What sectors are in my ETFs?'),
 ('overview','What is the account value?'),('overview','Summarize my portfolio'),
 ('performance_unavailable','Explain benchmark performance'),('risk_unavailable','Tell me the Sharpe ratio'),
 ('xray','Is this too concentrated?'),('overview','Analyze my investment holdings')]
HOLDINGS_DEMO=[{'symbol':'ACME','name':'Acme Labs (fictional)','sector':'Technology','asset_class':'Equity','quantity':10,'avg_cost':70,'current_price':100},
               {'symbol':'ETF1','name':'Demo ETF One','sector':'Growth ETF','asset_class':'ETF','quantity':20,'avg_cost':75,'current_price':90},
               {'symbol':'ETF2','name':'Demo ETF Two','sector':'Broad Market ETF','asset_class':'ETF','quantity':15,'avg_cost':80,'current_price':100}]
CONSTITUENTS=[{'fund_symbol':'ETF1','underlying_symbol':'ACME','sector':'Technology','weight_pct':25,'as_of':'2026-11-01','source':'FICTIONAL_DEMO_DATA'},
              {'fund_symbol':'ETF2','underlying_symbol':'ACME','sector':'Technology','weight_pct':20,'as_of':'2026-11-01','source':'FICTIONAL_DEMO_DATA'}]
FIXTURES=[{'name':'fictional-growth','cash':1000,'is_demo':True,'holdings':HOLDINGS_DEMO,'constituents':CONSTITUENTS,'questions':QUESTIONS_DEMO},
          {'name':'user-imported-snapshot','cash':0,'is_demo':False,'holdings':HOLDINGS_DEMO,'constituents':[],'questions':QUESTIONS_IMPORTED},
          {'name':'user-imported-partial-etf','cash':250,'is_demo':False,'holdings':HOLDINGS_DEMO,'constituents':CONSTITUENTS,'questions':QUESTIONS_IMPORTED}]
