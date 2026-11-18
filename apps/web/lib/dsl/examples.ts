/** The three worked DSL examples from docs/architecture/05-strategy-dsl.md §10 (mirrors packages/strategy/src/strategy/dsl/examples.py). */

export const DSL_EXAMPLES: Record<string, { label: string; doc: Record<string, unknown> }> = {
  "ema_rsi_nifty": {
    "label": "NIFTY EMA momentum (5m)",
    "doc": {
      "dsl_schema_version": "1.0",
      "name": "NIFTY EMA Momentum",
      "origin": "user_nl",
      "language": "mr",
      "original_text": "EMA 9 \u0928\u0947 EMA 21 \u0932\u093e \u0935\u0930\u091a\u094d\u092f\u093e \u092c\u093e\u091c\u0942\u0928\u0947 cross \u0915\u0947\u0932\u094d\u092f\u093e\u0935\u0930 \u0906\u0923\u093f RSI 55 \u092a\u0947\u0915\u094d\u0937\u093e \u091c\u093e\u0938\u094d\u0924 \u0905\u0938\u0932\u094d\u092f\u093e\u0938 Buy \u0915\u0930\u093e.",
      "market": "NSE",
      "universe": {
        "kind": "underlying_future",
        "underlying": "NIFTY",
        "contract": {
          "expiry": "current_month",
          "roll_days_before_expiry": 1
        }
      },
      "timeframe": "5m",
      "session": {
        "product": "INTRADAY",
        "trade_start": "09:20",
        "no_new_entries_after": "14:45",
        "square_off_at": "15:15"
      },
      "regime_filters": [],
      "indicators": {
        "ema9": {
          "type": "EMA",
          "params": {
            "period": 9
          }
        },
        "ema21": {
          "type": "EMA",
          "params": {
            "period": 21
          }
        },
        "rsi14": {
          "type": "RSI",
          "params": {
            "period": 14
          }
        },
        "atr14": {
          "type": "ATR",
          "params": {
            "period": 14
          }
        }
      },
      "direction": "long_only",
      "entry": {
        "long": {
          "kind": "group",
          "op": "and",
          "conditions": [
            {
              "kind": "cross",
              "left": {
                "kind": "indicator",
                "id": "ema9"
              },
              "direction": "crosses_above",
              "right": {
                "kind": "indicator",
                "id": "ema21"
              }
            },
            {
              "kind": "compare",
              "left": {
                "kind": "indicator",
                "id": "rsi14"
              },
              "op": "gt",
              "right": {
                "kind": "const",
                "value": 55
              }
            }
          ]
        }
      },
      "exit": {
        "long": {
          "kind": "cross",
          "left": {
            "kind": "indicator",
            "id": "ema9"
          },
          "direction": "crosses_below",
          "right": {
            "kind": "indicator",
            "id": "ema21"
          }
        }
      },
      "stop_loss": {
        "unit": "atr",
        "value": 1.0,
        "atr_indicator_id": "atr14"
      },
      "target": {
        "unit": "atr",
        "value": 2.0,
        "atr_indicator_id": "atr14"
      },
      "position_sizing": {
        "method": "fixed_lots",
        "lots": 1,
        "max_lots": 1
      },
      "max_positions": 1,
      "max_trades_per_day": 3
    }
  },
  "banknifty_vwap_reversion": {
    "label": "BANKNIFTY VWAP reversion (5m)",
    "doc": {
      "dsl_schema_version": "1.0",
      "name": "BANKNIFTY VWAP Reversion",
      "origin": "user_visual",
      "market": "NSE",
      "universe": {
        "kind": "underlying_future",
        "underlying": "BANKNIFTY",
        "contract": {
          "expiry": "current_month"
        }
      },
      "timeframe": "5m",
      "context_timeframes": [
        "15m"
      ],
      "session": {
        "product": "INTRADAY",
        "trade_start": "09:45",
        "no_new_entries_after": "14:30",
        "square_off_at": "15:10",
        "trade_on_expiry_day": false
      },
      "regime_filters": [
        {
          "source": "adx",
          "indicator_id": "adx15",
          "max": 25
        },
        {
          "source": "vix",
          "min": 10,
          "max": 22
        }
      ],
      "time_filters": [
        {
          "start": "12:00",
          "end": "13:00",
          "mode": "block_entries"
        }
      ],
      "indicators": {
        "vwap": {
          "type": "VWAP",
          "params": {
            "anchor": "session"
          }
        },
        "rsi7": {
          "type": "RSI",
          "params": {
            "period": 7
          }
        },
        "atr14": {
          "type": "ATR",
          "params": {
            "period": 14
          }
        },
        "adx15": {
          "type": "ADX",
          "params": {
            "period": 14
          },
          "timeframe": "15m"
        }
      },
      "direction": "both",
      "entry": {
        "long": {
          "kind": "group",
          "op": "and",
          "conditions": [
            {
              "kind": "compare",
              "left": {
                "kind": "price",
                "field": "close"
              },
              "op": "lt",
              "right": {
                "kind": "indicator",
                "id": "vwap",
                "field": "lower_2"
              }
            },
            {
              "kind": "compare",
              "left": {
                "kind": "indicator",
                "id": "rsi7"
              },
              "op": "lt",
              "right": {
                "kind": "const",
                "value": 25
              }
            },
            {
              "kind": "slope",
              "value": {
                "kind": "indicator",
                "id": "rsi7"
              },
              "direction": "rising",
              "bars": 1
            }
          ]
        },
        "short": {
          "kind": "group",
          "op": "and",
          "conditions": [
            {
              "kind": "compare",
              "left": {
                "kind": "price",
                "field": "close"
              },
              "op": "gt",
              "right": {
                "kind": "indicator",
                "id": "vwap",
                "field": "upper_2"
              }
            },
            {
              "kind": "compare",
              "left": {
                "kind": "indicator",
                "id": "rsi7"
              },
              "op": "gt",
              "right": {
                "kind": "const",
                "value": 75
              }
            },
            {
              "kind": "slope",
              "value": {
                "kind": "indicator",
                "id": "rsi7"
              },
              "direction": "falling",
              "bars": 1
            }
          ]
        },
        "cooldown_bars": 3
      },
      "exit": {
        "time_exit_bars": 24
      },
      "stop_loss": {
        "unit": "atr",
        "value": 1.5,
        "atr_indicator_id": "atr14"
      },
      "target": {
        "unit": "indicator",
        "indicator_ref": {
          "kind": "indicator",
          "id": "vwap",
          "field": "value"
        }
      },
      "position_sizing": {
        "method": "risk_percent",
        "risk_percent": 0.5,
        "max_lots": 2
      },
      "max_positions": 1,
      "max_trades_per_day": 4
    }
  },
  "nifty50_daily_breakout": {
    "label": "NIFTY 50 daily breakout (1d)",
    "doc": {
      "dsl_schema_version": "1.0",
      "name": "NIFTY50 20-day Breakout",
      "origin": "ai_research",
      "market": "NSE",
      "universe": {
        "kind": "watchlist",
        "watchlist_id": "wl_nifty50_liquid"
      },
      "timeframe": "1d",
      "session": {
        "product": "DELIVERY",
        "allowed_weekdays": [
          0,
          1,
          2,
          3,
          4
        ]
      },
      "regime_filters": [
        {
          "source": "daily_trend",
          "allowed": [
            "up"
          ]
        }
      ],
      "indicators": {
        "hh20": {
          "type": "SWING",
          "params": {
            "left": 20,
            "right": 0
          }
        },
        "ema50": {
          "type": "EMA",
          "params": {
            "period": 50
          }
        },
        "volsma": {
          "type": "VOLUME_SMA",
          "params": {
            "period": 20
          }
        },
        "atr14": {
          "type": "ATR",
          "params": {
            "period": 14
          }
        },
        "trend": {
          "type": "DAILY_TREND",
          "params": {
            "fast": 20,
            "slow": 50
          }
        }
      },
      "direction": "long_only",
      "entry": {
        "long": {
          "kind": "group",
          "op": "and",
          "conditions": [
            {
              "kind": "compare",
              "left": {
                "kind": "price",
                "field": "close"
              },
              "op": "gt",
              "right": {
                "kind": "indicator",
                "id": "hh20",
                "field": "last_high",
                "offset": 1
              }
            },
            {
              "kind": "compare",
              "left": {
                "kind": "price",
                "field": "close"
              },
              "op": "gt",
              "right": {
                "kind": "indicator",
                "id": "ema50"
              }
            },
            {
              "kind": "compare",
              "left": {
                "kind": "price",
                "field": "volume"
              },
              "op": "gt",
              "right": {
                "kind": "arith",
                "op": "*",
                "left": {
                  "kind": "indicator",
                  "id": "volsma"
                },
                "right": {
                  "kind": "const",
                  "value": 1.5
                }
              }
            }
          ]
        }
      },
      "exit": {
        "long": {
          "kind": "compare",
          "left": {
            "kind": "price",
            "field": "close"
          },
          "op": "lt",
          "right": {
            "kind": "indicator",
            "id": "ema50"
          }
        },
        "time_exit_bars": 40
      },
      "stop_loss": {
        "unit": "atr",
        "value": 2.0,
        "atr_indicator_id": "atr14"
      },
      "target": {
        "rr_multiple": 3.0,
        "unit": "atr",
        "value": 6.0,
        "atr_indicator_id": "atr14",
        "partial": [
          {
            "at": {
              "unit": "atr",
              "value": 3.0,
              "atr_indicator_id": "atr14"
            },
            "close_pct": 50,
            "move_stop_to_breakeven": true
          }
        ]
      },
      "trailing": {
        "mode": "atr",
        "value": 2.5,
        "atr_indicator_id": "atr14",
        "activate_after": {
          "unit": "atr",
          "value": 3.0,
          "atr_indicator_id": "atr14"
        }
      },
      "position_sizing": {
        "method": "risk_percent",
        "risk_percent": 1.0,
        "max_capital_pct": 15
      },
      "max_positions": 5,
      "max_trades_per_day": 2,
      "fill": {
        "entry_order_type": "LIMIT_AT_CLOSE",
        "limit_timeout_bars": 1
      }
    }
  }
};
