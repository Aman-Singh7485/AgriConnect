from flask import Flask, render_template, request, jsonify
from db import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)


@app.route("/")
@app.route("/index.html")
def home():
    connection = get_db_connection()

    if not connection:
        return "Database connection failed", 500

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("SELECT COUNT(*) AS total_users FROM users")
        total_users = cursor.fetchone()["total_users"]

        cursor.execute("""
            SELECT COUNT(*) AS verified_shopkeepers
            FROM users
            WHERE role = 'shopkeeper'
              AND is_verified = 1
        """)
        verified_shopkeepers = cursor.fetchone()["verified_shopkeepers"]

        cursor.execute("""
            SELECT COUNT(*) AS successful_orders
            FROM orders
            WHERE status = 'completed'
        """)
        successful_orders = cursor.fetchone()["successful_orders"]

        cursor.execute("""
            SELECT COALESCE(SUM(total_amount), 0) AS trade_value
            FROM orders
            WHERE status = 'completed'
        """)
        trade_value = float(cursor.fetchone()["trade_value"])

        cursor.execute("""
            SELECT COALESCE(AVG(rating), 0) AS average_rating
            FROM reviews
        """)
        average_rating = round(float(cursor.fetchone()["average_rating"]), 1)

        return render_template(
            "index.html",
            total_users=total_users,
            verified_shopkeepers=verified_shopkeepers,
            successful_orders=successful_orders,
            trade_value=trade_value,
            average_rating=average_rating
        )

    except Exception as error:
        print(f"Homepage statistics error: {error}")
        return "Could not load homepage statistics.", 500

    finally:
        cursor.close()
        connection.close()


@app.route("/test-db")
def test_db():
    connection = get_db_connection()

    if connection and connection.is_connected():
        cursor = connection.cursor()
        cursor.execute("SELECT DATABASE();")
        database_name = cursor.fetchone()[0]

        cursor.close()
        connection.close()

        return f"Connected successfully to MySQL database: {database_name}"

    return "Database connection failed", 500


@app.route("/api/signup", methods=["POST"])
def api_signup():
    data = request.get_json() or {}

    full_name = data.get("fullName", "").strip()
    username = data.get("username", "").strip()
    mobile = data.get("mobile", "").strip()
    location = data.get("location", "").strip()
    password = data.get("password", "")
    role = data.get("role", "").strip()

    if not all([full_name, username, mobile, location, password, role]):
        return jsonify({
            "success": False,
            "message": "All fields are required."
        }), 400

    if role not in ("farmer", "shopkeeper"):
        return jsonify({
            "success": False,
            "message": "Invalid role."
        }), 400

    connection = get_db_connection()

    if not connection:
        return jsonify({
            "success": False,
            "message": "Database connection failed."
        }), 500

    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO users
            (
                full_name,
                username,
                mobile,
                location,
                password_hash,
                role,
                is_verified
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                full_name,
                username,
                mobile,
                location,
                generate_password_hash(password),
                role,
                0
            )
        )
        connection.commit()

        return jsonify({
            "success": True,
            "message": "Account created successfully."
        }), 201

    except Exception as error:
        connection.rollback()
        print(f"Signup database error: {error}")

        if getattr(error, "errno", None) == 1062:
            return jsonify({
                "success": False,
                "message": "Username or mobile number already exists."
            }), 409

        return jsonify({
            "success": False,
            "message": "Could not create account."
        }), 500

    finally:
        cursor.close()
        connection.close()


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}

    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "").strip()

    if not username or not password or not role:
        return jsonify({
            "success": False,
            "message": "Username, password and role are required."
        }), 400

    if role not in ("farmer", "shopkeeper"):
        return jsonify({
            "success": False,
            "message": "Invalid role."
        }), 400

    connection = get_db_connection()

    if not connection:
        return jsonify({
            "success": False,
            "message": "Database connection failed."
        }), 500

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT id, full_name, username, mobile, location, password_hash, role
            FROM users
            WHERE username = %s OR mobile = %s
            """,
            (username, username)
        )

        user = cursor.fetchone()

        if not user:
            return jsonify({
                "success": False,
                "message": "User not found."
            }), 401

        if user["role"] != role:
            return jsonify({
                "success": False,
                "message": "Selected role does not match this account."
            }), 401

        if not check_password_hash(user["password_hash"], password):
            return jsonify({
                "success": False,
                "message": "Incorrect password."
            }), 401

        return jsonify({
            "success": True,
            "message": "Login successful.",
            "user": {
                "id": user["id"],
                "full_name": user["full_name"],
                "username": user["username"],
                "mobile": user["mobile"],
                "location": user["location"],
                "role": user["role"]
            }
        }), 200

    except Exception as error:
        print(f"Login database error: {error}")

        return jsonify({
            "success": False,
            "message": "Could not log in."
        }), 500

    finally:
        cursor.close()
        connection.close()


@app.route("/api/grain-listings", methods=["POST"])
def add_grain_listing():
    data = request.get_json() or {}

    required_fields = [
        "farmer_id",
        "grain_name",
        "quantity",
        "price",
        "latitude",
        "longitude"
    ]

    missing_fields = [
        field for field in required_fields
        if data.get(field) in (None, "")
    ]

    if missing_fields:
        return jsonify({
            "success": False,
            "message": f"Missing fields: {', '.join(missing_fields)}"
        }), 400

    try:
        farmer_id = int(data["farmer_id"])
        quantity = float(data["quantity"])
        price = float(data["price"])
        latitude = float(data["latitude"])
        longitude = float(data["longitude"])

        if quantity <= 0 or price <= 0:
            raise ValueError

    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Quantity and price must be greater than zero."
        }), 400

    connection = get_db_connection()

    if not connection:
        return jsonify({
            "success": False,
            "message": "Database connection failed."
        }), 500

    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO grain_listings
            (
                farmer_id,
                grain_name,
                quantity,
                unit,
                price_per_quintal,
                description,
                status,
                latitude,
                longitude
            )
            VALUES (%s, %s, %s, 'kg', %s, %s, 'available', %s, %s)
            """,
            (
                farmer_id,
                data["grain_name"].strip(),
                quantity,
                price,
                data.get("description", "").strip(),
                latitude,
                longitude
            )
        )

        connection.commit()
        listing_id = cursor.lastrowid

        return jsonify({
            "success": True,
            "message": "Grain listing saved successfully in kg.",
            "listing_id": listing_id
        }), 201

    except Exception as error:
        connection.rollback()
        print(f"Grain listing database error: {error}")

        return jsonify({
            "success": False,
            "message": "Could not save grain listing."
        }), 500

    finally:
        cursor.close()
        connection.close()

@app.route("/api/grain-listings", methods=["GET"])
def get_nearby_grain_listings():
    try:
        buyer_latitude = float(request.args.get("latitude"))
        buyer_longitude = float(request.args.get("longitude"))
        radius_km = float(request.args.get("radius", 50))

        if radius_km <= 0 or radius_km > 200:
            return jsonify({
                "success": False,
                "message": "Radius must be between 1 and 200 km."
            }), 400

    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Valid latitude and longitude are required."
        }), 400

    connection = get_db_connection()

    if not connection:
        return jsonify({
            "success": False,
            "message": "Database connection failed."
        }), 500

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                grain_listings.id,
                grain_listings.grain_name,
                grain_listings.quantity,
                grain_listings.unit,
                grain_listings.price_per_quintal,
                grain_listings.description,
                grain_listings.status,
                grain_listings.latitude,
                grain_listings.longitude,
                users.full_name AS farmer_name,
                users.location AS farmer_location,
                (
                    6371 * ACOS(
                        LEAST(
                            1.0,
                            COS(RADIANS(%s))
                            * COS(RADIANS(grain_listings.latitude))
                            * COS(
                                RADIANS(grain_listings.longitude) - RADIANS(%s)
                            )
                            + SIN(RADIANS(%s))
                            * SIN(RADIANS(grain_listings.latitude))
                        )
                    )
                ) AS distance_km
            FROM grain_listings
            INNER JOIN users
                ON grain_listings.farmer_id = users.id
            WHERE grain_listings.status = 'available'
                AND grain_listings.quantity > 0
                AND grain_listings.latitude IS NOT NULL
                AND grain_listings.longitude IS NOT NULL
            HAVING distance_km <= %s
            ORDER BY distance_km ASC
            """,
            (
                buyer_latitude,
                buyer_longitude,
                buyer_latitude,
                radius_km
            )
        )

        listings = cursor.fetchall()

        for listing in listings:
            listing["quantity"] = float(listing["quantity"])
            listing["price_per_quintal"] = float(listing["price_per_quintal"])
            listing["latitude"] = float(listing["latitude"])
            listing["longitude"] = float(listing["longitude"])
            listing["distance_km"] = round(float(listing["distance_km"]), 2)

        return jsonify({
            "success": True,
            "count": len(listings),
            "listings": listings
        }), 200

    except Exception as error:
        print(f"Fetch grain listings error: {error}")

        return jsonify({
            "success": False,
            "message": "Could not fetch grain listings."
        }), 500

    finally:
        cursor.close()
        connection.close()


@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.get_json() or {}

    try:
        listing_id = int(data.get("listing_id"))
        buyer_id = int(data.get("buyer_id"))
        quantity = float(data.get("quantity"))
        delivery_address = data.get("delivery_address", "").strip()

        if quantity <= 0:
            raise ValueError

    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Valid listing ID, buyer ID, and quantity in kg are required."
        }), 400

    connection = get_db_connection()

    if not connection:
        return jsonify({
            "success": False,
            "message": "Database connection failed."
        }), 500

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT id, role
            FROM users
            WHERE id = %s
            """,
            (buyer_id,)
        )
        buyer = cursor.fetchone()

        if not buyer or buyer["role"] != "shopkeeper":
            return jsonify({
                "success": False,
                "message": "Only a shopkeeper can place an order."
            }), 403

        cursor.execute(
            """
            SELECT
                id,
                farmer_id,
                grain_name,
                quantity,
                unit,
                price_per_quintal,
                status
            FROM grain_listings
            WHERE id = %s
            FOR UPDATE
            """,
            (listing_id,)
        )
        listing = cursor.fetchone()

        if not listing:
            return jsonify({
                "success": False,
                "message": "Grain listing not found."
            }), 404

        if listing["status"] != "available":
            return jsonify({
                "success": False,
                "message": "This grain listing is no longer available."
            }), 400

        if listing["unit"] != "kg":
            return jsonify({
                "success": False,
                "message": "This listing is not yet configured in kg. Create a new kg listing."
            }), 400

        available_quantity = float(listing["quantity"])

        if quantity > available_quantity:
            return jsonify({
                "success": False,
                "message": f"Only {available_quantity:g} kg is available."
            }), 400

        price_per_kg = float(listing["price_per_quintal"])
        total_amount = quantity * price_per_kg
        remaining_quantity = available_quantity - quantity
        new_listing_status = "sold" if remaining_quantity == 0 else "available"

        cursor.execute(
            """
            INSERT INTO orders
            (
                listing_id,
                buyer_id,
                quantity,
                total_amount,
                status,
                delivery_address
            )
            VALUES (%s, %s, %s, %s, 'pending', %s)
            """,
            (
                listing_id,
                buyer_id,
                quantity,
                total_amount,
                delivery_address
            )
        )

        order_id = cursor.lastrowid

        cursor.execute(
            """
            UPDATE grain_listings
            SET quantity = %s,
                status = %s
            WHERE id = %s
            """,
            (
                remaining_quantity,
                new_listing_status,
                listing_id
            )
        )

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Order placed successfully.",
            "order_id": order_id,
            "remaining_quantity": remaining_quantity,
            "listing_status": new_listing_status
        }), 201

    except Exception as error:
        connection.rollback()
        print(f"Create order error: {error}")

        return jsonify({
            "success": False,
            "message": "Could not place the order."
        }), 500

    finally:
        cursor.close()
        connection.close()

@app.route("/api/farmer-orders", methods=["GET"])
def get_farmer_orders():
    try:
        farmer_id = int(request.args.get("farmer_id"))
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "A valid farmer ID is required."
        }), 400

    connection = get_db_connection()

    if not connection:
        return jsonify({
            "success": False,
            "message": "Database connection failed."
        }), 500

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                orders.id,
                orders.quantity,
                orders.total_amount,
                orders.status,
                orders.delivery_address,
                orders.created_at,
                grain_listings.grain_name,
                grain_listings.unit,
                users.full_name AS buyer_name
            FROM orders
            INNER JOIN grain_listings
                ON orders.listing_id = grain_listings.id
            INNER JOIN users
                ON orders.buyer_id = users.id
            WHERE grain_listings.farmer_id = %s
            ORDER BY orders.created_at DESC
            """,
            (farmer_id,)
        )

        orders = cursor.fetchall()

        for order in orders:
            order["quantity"] = float(order["quantity"])
            order["total_amount"] = float(order["total_amount"])
            order["created_at"] = order["created_at"].isoformat() if order["created_at"] else None

        return jsonify({
            "success": True,
            "orders": orders
        }), 200

    except Exception as error:
        print(f"Fetch farmer orders error: {error}")

        return jsonify({
            "success": False,
            "message": "Could not fetch farmer orders."
        }), 500

    finally:
        cursor.close()
        connection.close()


@app.route("/api/buyer-orders", methods=["GET"])
def get_buyer_orders():
    try:
        buyer_id = int(request.args.get("buyer_id"))
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "A valid buyer ID is required."
        }), 400

    connection = get_db_connection()

    if not connection:
        return jsonify({
            "success": False,
            "message": "Database connection failed."
        }), 500

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                orders.id,
                orders.quantity,
                orders.total_amount,
                orders.status,
                orders.delivery_address,
                orders.created_at,
                grain_listings.grain_name,
                grain_listings.unit,
                farmers.full_name AS farmer_name
            FROM orders
            INNER JOIN grain_listings
                ON orders.listing_id = grain_listings.id
            INNER JOIN users AS farmers
                ON grain_listings.farmer_id = farmers.id
            WHERE orders.buyer_id = %s
            ORDER BY orders.created_at DESC
            """,
            (buyer_id,)
        )

        orders = cursor.fetchall()

        for order in orders:
            order["quantity"] = float(order["quantity"])
            order["total_amount"] = float(order["total_amount"])
            order["created_at"] = order["created_at"].isoformat() if order["created_at"] else None

        return jsonify({
            "success": True,
            "orders": orders
        }), 200

    except Exception as error:
        print(f"Fetch buyer orders error: {error}")

        return jsonify({
            "success": False,
            "message": "Could not fetch buyer orders."
        }), 500

    finally:
        cursor.close()
        connection.close()


@app.route("/api/orders/<int:order_id>/status", methods=["PATCH"])
def update_order_status(order_id):
    data = request.get_json() or {}

    try:
        farmer_id = int(data.get("farmer_id"))
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "A valid farmer ID is required."
        }), 400

    new_status = data.get("status", "").strip()

    if new_status not in ("accepted", "rejected", "completed"):
        return jsonify({
            "success": False,
            "message": "Invalid order status."
        }), 400

    connection = get_db_connection()

    if not connection:
        return jsonify({
            "success": False,
            "message": "Database connection failed."
        }), 500

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                orders.id,
                orders.listing_id,
                orders.quantity,
                orders.status,
                grain_listings.farmer_id
            FROM orders
            INNER JOIN grain_listings
                ON orders.listing_id = grain_listings.id
            WHERE orders.id = %s
            FOR UPDATE
            """,
            (order_id,)
        )
        order = cursor.fetchone()

        if not order:
            return jsonify({
                "success": False,
                "message": "Order not found."
            }), 404

        if order["farmer_id"] != farmer_id:
            return jsonify({
                "success": False,
                "message": "You are not authorized to update this order."
            }), 403

        current_status = order["status"]

        valid_changes = {
            "pending": ("accepted", "rejected"),
            "accepted": ("completed",)
        }

        if new_status not in valid_changes.get(current_status, ()):
            return jsonify({
                "success": False,
                "message": f"Cannot change a {current_status} order to {new_status}."
            }), 400

        if new_status == "rejected":
            cursor.execute(
                """
                UPDATE grain_listings
                SET quantity = quantity + %s,
                    status = 'available'
                WHERE id = %s
                """,
                (
                    float(order["quantity"]),
                    order["listing_id"]
                )
            )

        cursor.execute(
            """
            UPDATE orders
            SET status = %s
            WHERE id = %s
            """,
            (new_status, order_id)
        )

        connection.commit()

        messages = {
            "accepted": "Order accepted successfully.",
            "rejected": "Order rejected and grain quantity restored.",
            "completed": "Order marked as completed successfully."
        }

        return jsonify({
            "success": True,
            "message": messages[new_status]
        }), 200

    except Exception as error:
        connection.rollback()
        print(f"Update order status error: {error}")

        return jsonify({
            "success": False,
            "message": "Could not update the order status."
        }), 500

    finally:
        cursor.close()
        connection.close()


@app.route("/login")
@app.route("/login.html")
def login():
    return render_template("login.html")


@app.route("/signup")
@app.route("/signup.html")
def signup():
    return render_template("signup.html")


@app.route("/farmer-dashboard")
@app.route("/farmer-dashboard.html")
def farmer_dashboard():
    return render_template("farmer-dashboard.html")


@app.route("/shopkeeper-dashboard")
@app.route("/shopkeeper-dashboard.html")
def shopkeeper_dashboard():
    return render_template("shopkeeper-dashboard.html")


if __name__ == "__main__":
    app.run(debug=True)