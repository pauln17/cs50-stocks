import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Show portfolio of stocks"""
    # Grab information from stocks and group similar symbols together that have more than 0 shares.
    user_id = session["user_id"]
    stock_info = db.execute(
        "SELECT symbol, name, SUM(shares) as shares, price FROM stocks where id = ? GROUP BY symbol HAVING SUM(shares) > 0", user_id)

    cash_bal = db.execute("SELECT cash FROM users where id = ?", user_id)[0]['cash']

    # Determine total worth of account by adding up price of each stock in account
    total = cash_bal
    for holdings in stock_info:
        total += holdings["price"] * holdings["shares"]

    return render_template("index.html", stock_info=stock_info, usd=usd, cash_bal=usd(cash_bal), total=usd(total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")

    symbol = request.form.get("symbol")
    quotes = lookup(symbol)

    # If symbol is valid, check the amount of shares user wants to buy for empty input, negative integers, non-numeric inputs or insufficient cash. Then update the database accordingly if all checks are passed.
    if quotes:
        symbol = quotes["symbol"]
        name = quotes["name"]
        price = quotes["price"]
        shares = request.form.get("shares")
        if shares.isdigit() != True:
            return apology("Invalid Shares", 400)
        elif int(shares) <= 0:
            return apology("Invalid Shares", 400)
        elif not shares:
            return apology("Invalid Shares", 400)

        shares = int(shares)
        user_id = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]

        purchase_balance = cash - price*shares
        if purchase_balance < 0:
            return apology("Insufficient Cash", 400)
        transactions = "Buy"
        db.execute("UPDATE users SET cash = ? WHERE id = ?", purchase_balance, user_id)
        db.execute("INSERT INTO stocks (id, symbol, name, price, shares, transactions, timestamp) VALUES(?, ?, ?, ?, ?, ?, ?)",
                   user_id, symbol, name, price, shares, transactions, datetime.now())

    else:
        return apology("Invalid Symbol", 400)

    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Grab information from stocks table that displays required info for transaction history - symbol, name, price at purchase, amount of shares bought/sold, transaction type
    user_id = session["user_id"]
    transaction_info = db.execute("SELECT * FROM stocks WHERE id = ?", user_id)

    return render_template("history.html", transaction_info=transaction_info)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # Use the given lookup function to determine if a symbol is valid, and if so, display the information given by lookup - name, price, symbol
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quotes = lookup(symbol)

        if not quotes:
            return apology("Symbol not found", 400)

        return render_template("quoted.html", usd=usd, name=quotes["name"], price=quotes["price"], symbol=quotes["symbol"])

    elif request.method == "GET":
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        password_confirmation = request.form.get("confirmation")

        # Determining valid username and password inputs
        if not username:
            return apology("Empty Username", 400)
        elif not password:
            return apology("Empty Password", 400)
        elif not password_confirmation:
            return apology("Empty Confirmation Password", 400)
        elif password != password_confirmation:
            return apology("Passwords do not match", 400)

        password_hash = generate_password_hash(password)

        # Attempt to add username and password into database, if fails, then username already exists
        try:
            db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", username, password_hash)
        except:
            return apology("Username Taken")

    elif request.method == "GET":
        return render_template("register.html")

    return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]
    if request.method == "GET":
        stock_info = db.execute("SELECT symbol FROM stocks WHERE id = ? GROUP BY symbol", user_id)
        return render_template("sell.html", stock_info=stock_info)

    symbol = request.form.get("symbol")
    quotes = lookup(symbol)

    # If the symbol is valid, check if share is a viable number and if so, sell those shares and update database accordingly
    if quotes:
        symbol = request.form.get("symbol")
        quotes = lookup(symbol)
        price = quotes["price"]
        name = quotes["name"]
        shares = int(request.form.get("shares"))

        stock_info = db.execute(
            "SELECT SUM(shares) as shares FROM stocks WHERE symbol = ? AND id = ? GROUP BY symbol", symbol, user_id)

        if shares <= 0:
            return apology("Shares must be greater than 0")
        elif shares > stock_info[0]["shares"]:
            return apology("You don't have enough shares")

        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
        sell_balance = cash + price*shares
        db.execute("UPDATE users SET cash = ? WHERE id = ?", sell_balance, user_id)
        transactions = "Sell"

        db.execute("INSERT INTO stocks (id, symbol, name, price, shares, transactions, timestamp) VALUES(?, ?, ?, ?, ?, ?, ?)",
                   user_id, symbol, name, price, -shares, transactions, datetime.now())

        shares_check = db.execute(
            "SELECT SUM(shares) as shares FROM stocks WHERE symbol = ? AND id = ? GROUP BY symbol", symbol, user_id)
        if shares_check[0]["shares"] == 0:
            db.execute("DELETE FROM stocks WHERE id = ? AND symbol = ?", user_id, symbol)

    else:
        return apology("Invalid Symbol", 400)

    return redirect("/")


@app.route("/cash", methods=["GET", "POST"])
@login_required
def add_cash():

    # Display a deposit form with account balance
    user_id = session["user_id"]
    cash_balance = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
    if request.method == "GET":
        return render_template("cash.html", usd=usd, cash_balance=usd(cash_balance))
    else:
        # Deposit cash by updating database against user deposit amount
        cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
        deposit_amount = request.form.get("deposit")
        total_balance = int(deposit_amount) + int(cash)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", total_balance, user_id)

    return redirect("/")