import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

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


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response




@app.route("/")
@login_required
def index():

    #Query DB for users tranaactions
    stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING total_shares > 0",
                              session["user_id"])

    holdings = []
    grand_total = 0

    # Iterate over each transaction, get the current stock price and calculate total value
    for stock in stocks:
        stock_data = lookup(stock["symbol"])
        total = stock_data["price"] * stock["total_shares"]
        holdings.append({
            "symbol": stock["symbol"],
            "shares": stock["total_shares"],
            "current_price": stock_data["price"],
            "total": usd(total)
        })

        grand_total += total

    #users current cash balance
    cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]['cash']
    grand_total += cash


    return render_template("index.html", database=holdings, cash=usd(cash), grand_total=usd(grand_total))




@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")

        if not symbol:
            return apology("Must provide stock symbol", 400)
        if not shares:
            return apology("Must provide number of shares", 400)

        #positive int
        if not shares.isdigit() or int(shares) < 1:
            return apology("Shares must be a positive integer", 400)

        shares = int(shares)

        #current price of stock
        stock = lookup(symbol)
        if stock is None:
            return apology("Invalid stock symbol", 400)

        #get current cash of user
        rows = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cash = rows[0]["cash"]

        #calulate purchase cost
        total_cost = shares * stock["price"]

        if total_cost > cash:
            return apology("You can't afford this purchase", 400)

        #update user cash
        db.execute("UPDATE users SET cash =  cash - ? WHERE id = ?", total_cost, session["user_id"])

        #insert purchase into transation table
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                   session["user_id"], symbol, shares, stock["price"])

        flash(f"Bought {shares} shares of {symbol} for {usd(total_cost)}!")
        return redirect("/")

    else:
        return render_template("buy.html")



@app.route("/history")
@login_required
def history():
    transactions = db.execute("SELECT symbol, shares, price, date FROM transactions WHERE user_id = ? ORDER BY date DESC",
                              session["user_id"])
    return render_template("history.html", transactions=transactions)


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
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        stock = lookup(symbol)

        if stock is None:
            return apology("Invalid symbol", 400)

        return render_template("quoted.html", name=stock["name"], price=stock["price"], symbol=stock["symbol"])

    else:
        return render_template("quote.html")



@app.route("/register", methods=["GET", "POST"])
def register():

    session.clear()
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        #Ensure confirmation password was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide confirmation password", 400)

        #Maatch
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("password do not match", 400)

        #Check DB for usernames and if it already exist, message
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        if len(rows) != 0:
            return apology("username already exist", 400)

        #Insert to DB
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)",
                request.form.get("username"), generate_password_hash(request.form.get("password")))

        #Query database for new user
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    else:
        return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    if request.method == "POST":
        symbol = request.form.get("symbol")
        try:
            shares = int(request.form.get("shares"))
        except ValueError:
            return apology("shares must be a positive interger", 400)

        if symbol == None or symbol == "":
            return apology("must select a stock to sell")
        elif shares <= 0:
            return apology("can't sell less than 0 shares", 400)

        stock = lookup(symbol)
        if stock == None:
            return apology("invalid symbol", 400)

        rows = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id AND symbol = :symbol GROUP BY symbol",
                          user_id=session["user_id"], symbol=symbol)

        if len(rows) != 1 or rows[0]["total_shares"] < shares:
            return apology("not enough shares", 400)

        price = shares * stock["price"]
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                   session["user_id"], symbol, -shares, price)
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?",
                   price, session["user_id"])

        flash(f"Sold {shares} shares of {symbol} for {usd(price)}!")
        return redirect("/")
    else:
        stocks = db.execute("SELECT DISTINCT symbol FROM transactions WHERE user_id = ?",
                            session["user_id"])

        return render_template("sell.html", stocks=stocks)


@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    #Allow user to add cash to their user account.

    if request.method == "POST":
        amount = request.form.get("amount")
        if not amount:
            return apology("Must provide amount", 403)

        #check if valid amount
        try:
            amount = float(amount)
            if amount <= 0:
                return apology("Invalid amount", 403)
        except ValueError:
            return apology("Invalid amount", 403)

        #update user cash
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", amount, session["user_id"])

        flash("added successfully!")
        return redirect("/")
    else:
        return render_template("add_cash.html")

