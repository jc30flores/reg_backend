import os
from flask import Flask, jsonify, request
from flask_cors import CORS, cross_origin
from dotenv import load_dotenv
import psycopg2
from psycopg2 import errors as pg_errors
from psycopg2.extras import RealDictCursor

# Load environment variables from .env file
load_dotenv()

# Database configuration from environment
DB_HOST = os.getenv("PG_HOST", "cfls9h51f4i86c.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com")
DB_NAME = os.getenv("PG_DATABASE", "dfc2jmocqkio6k")
DB_USER = os.getenv("PG_USER", "uf6s7k0lvso94d")
DB_PASSWORD = os.getenv("PG_PASSWORD", "p26334802041005114bc98db3c5f0766326cca1abea7a6899ef860a12e79b95e8")
DB_PORT = os.getenv("PG_PORT", "5432")

def get_db_connection():
    """
    Establishes a new database connection using psycopg2.
    Returns a connection object.
    """
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )
    return conn

# Initialize Flask app
app = Flask(__name__)
# Configure CORS to allow requests from the frontend
CORS(app, origins="*", supports_credentials=True)
@app.after_request
def apply_cors_headers(response):
    """
    Ensure CORS headers are set on all responses, including preflight OPTIONS.
    """
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,PUT,POST,DELETE,OPTIONS"
    return response
# Ensure 'shape', 'rotation', and 'color' columns exist in 'tables'
try:
    conn = get_db_connection()
    cur = conn.cursor()
    # Add shape column if missing
    cur.execute("ALTER TABLE tables ADD COLUMN IF NOT EXISTS shape TEXT;")
    # Add rotation and color columns for table orientation and coloring
    cur.execute("ALTER TABLE tables ADD COLUMN IF NOT EXISTS rotation INT NOT NULL DEFAULT 0;")
    cur.execute("ALTER TABLE tables ADD COLUMN IF NOT EXISTS color TEXT;")
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not ensure 'shape' column: {e}")

# Ensure map_elements table exists for custom map objects
try:
    conn = get_db_connection()
    cur = conn.cursor()
    # Create the map_elements table if it does not exist (with color column support)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS map_elements (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        type TEXT NOT NULL,
        position_x INT NOT NULL,
        position_y INT NOT NULL,
        width INT NOT NULL DEFAULT 0,
        height INT NOT NULL DEFAULT 0,
        rotation INT NOT NULL DEFAULT 0,
        content TEXT,
        color TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """)
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not ensure 'map_elements' table: {e}")

"""
Ensure 'color' and 'section_id' columns exist in 'map_elements', and 'access_code' column in 'employees'.
"""
try:
    conn = get_db_connection()
    cur = conn.cursor()
    # Add color column if missing
    cur.execute("ALTER TABLE map_elements ADD COLUMN IF NOT EXISTS color TEXT;")
    # Add section_id column to link elements to a restaurant section
    cur.execute("ALTER TABLE map_elements ADD COLUMN IF NOT EXISTS section_id UUID;")
    # Add font_size and font_style columns for text elements
    cur.execute("ALTER TABLE map_elements ADD COLUMN IF NOT EXISTS font_size INT;")
    cur.execute("ALTER TABLE map_elements ADD COLUMN IF NOT EXISTS font_style TEXT;")
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not ensure 'color' or 'section_id' columns: {e}")

# Ensure 'access_code' column exists in 'employees'
try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("ALTER TABLE employees ADD COLUMN IF NOT EXISTS access_code TEXT;")
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not ensure 'access_code' column in 'employees': {e}")

# -------------------------------------------------------------
# Menu Categories Table (for Menu Management)
# -------------------------------------------------------------

# Ensure menu_categories table exists
try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS menu_categories (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    conn.commit()

    # Seed default categories if empty
    cur.execute("SELECT COUNT(*) FROM menu_categories;")
    if cur.fetchone()[0] == 0:
        default_cats = ["Breakfast", "Lunch", "Dinner"]
        for cat in default_cats:
            cur.execute("INSERT INTO menu_categories (name) VALUES (%s) ON CONFLICT DO NOTHING;", (cat,))
        conn.commit()

    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not ensure 'menu_categories' table: {e}")

# -------------------------------------------------------------
# Menu Categories API
# -------------------------------------------------------------

@app.route('/api/menu-categories', methods=['GET', 'POST', 'OPTIONS'])
@cross_origin()
def menu_categories_collection():
    if request.method == 'GET':
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM menu_categories ORDER BY name;")
        cats = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(cats)

    # POST – create new category
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    # Title-case normalization (Pascal/Title)
    name = ' '.join([w.capitalize() for w in name.split()])

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "INSERT INTO menu_categories (name) VALUES (%s) RETURNING *;",
            (name,)
        )
        new_cat = cur.fetchone()
        conn.commit()
    except pg_errors.UniqueViolation:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': 'Category already exists'}), 409
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': str(e)}), 500

    cur.close()
    conn.close()
    return jsonify(new_cat), 201


@app.route('/api/menu-categories/<string:cat_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@cross_origin()
def menu_category_item(cat_id):
    if request.method == 'PUT':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        name = ' '.join([w.capitalize() for w in name.split()])

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(
                "UPDATE menu_categories SET name = %s, updated_at = NOW() WHERE id = %s RETURNING *;",
                (name, cat_id)
            )
            updated = cur.fetchone()
            conn.commit()
        except pg_errors.UniqueViolation:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({'error': 'Category already exists'}), 409
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({'error': str(e)}), 500

        cur.close()
        conn.close()
        if updated:
            return jsonify(updated)
        return jsonify({'error': 'Category not found'}), 404

    # DELETE
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # First delete related menu_items
    cur.execute("SELECT name FROM menu_categories WHERE id = %s;", (cat_id,))
    cat_row = cur.fetchone()
    if cat_row:
        cat_name = cat_row['name']
        cur.execute("DELETE FROM menu_items WHERE LOWER(category) = LOWER(%s);", (cat_name,))

    cur.execute("DELETE FROM menu_categories WHERE id = %s RETURNING id;", (cat_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if deleted:
        return jsonify({'id': deleted['id']})
    return jsonify({'error': 'Category not found'}), 404

# -------------------------------------------------------------
# Menu Sub-categories table and API
# -------------------------------------------------------------

# Ensure menu_subcategories exists
try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS menu_subcategories (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            category_id UUID REFERENCES menu_categories(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (category_id, name)
        );
        """
    )
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not ensure 'menu_subcategories' table: {e}")


@app.route('/api/subcategories', methods=['GET', 'POST', 'OPTIONS'])
@cross_origin()
def subcategories_collection():
    if request.method == 'GET':
        cat_id = request.args.get('category_id')
        sql = "SELECT * FROM menu_subcategories"
        params = ()
        if cat_id:
            sql += " WHERE category_id = %s"
            params = (cat_id,)
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(rows)

    # POST
    data = request.get_json() or {}
    name        = data.get('name', '').strip()
    category_id = data.get('category_id')
    if not name or not category_id:
        return jsonify({'error': 'name and category_id required'}), 400

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "INSERT INTO menu_subcategories (name, category_id) VALUES (%s, %s) RETURNING *;",
            (name.title(), category_id)
        )
        new_sub = cur.fetchone()
        conn.commit()
    except pg_errors.UniqueViolation:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': 'Subcategory already exists'}), 409
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': str(e)}), 500

    cur.close()
    conn.close()
    return jsonify(new_sub), 201


@app.route('/api/subcategories/<string:sub_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@cross_origin()
def subcategory_item(sub_id):
    if request.method == 'PUT':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'error': 'name required'}), 400
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(
                "UPDATE menu_subcategories SET name = %s, updated_at = NOW() WHERE id = %s RETURNING *;",
                (name.title(), sub_id)
            )
            updated = cur.fetchone()
            conn.commit()
        except pg_errors.UniqueViolation:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({'error': 'Subcategory already exists'}), 409
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({'error': str(e)}), 500
        cur.close()
        conn.close()
        if updated:
            return jsonify(updated)
        return jsonify({'error': 'Subcategory not found'}), 404

    # DELETE
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("DELETE FROM menu_subcategories WHERE id = %s RETURNING id;", (sub_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if deleted:
        return jsonify({'id': deleted['id']})
    return jsonify({'error': 'Subcategory not found'}), 404

# -------------------------------------------------------------
# Customization tables (groups, options, and menu item relations)
# -------------------------------------------------------------

# Ensure customization tables exist
try:
    conn = get_db_connection()
    cur = conn.cursor()
    # Ensure UUID extension for uuid_generate_v4()
    cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    # Create customization tables if missing
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS customization_groups (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name TEXT UNIQUE NOT NULL,
            is_required BOOLEAN DEFAULT FALSE,
            max_select INT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS customization_options (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            group_id UUID REFERENCES customization_groups(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            extra_price NUMERIC DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS menu_item_customizations (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            menu_item_id UUID REFERENCES menu_items(id) ON DELETE CASCADE,
            group_id UUID REFERENCES customization_groups(id) ON DELETE CASCADE
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS menu_item_customization_options (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            item_id UUID REFERENCES menu_items(id) ON DELETE CASCADE,
            option_id UUID REFERENCES customization_options(id) ON DELETE CASCADE
        );
        """
    )
    # Commit initial table creation
    conn.commit()
    # Ensure columns exist in menu_item_customizations
    cur.execute(
        "ALTER TABLE menu_item_customizations ADD COLUMN IF NOT EXISTS menu_item_id UUID REFERENCES menu_items(id) ON DELETE CASCADE;"
    )
    cur.execute(
        "ALTER TABLE menu_item_customizations ADD COLUMN IF NOT EXISTS group_id UUID REFERENCES customization_groups(id) ON DELETE CASCADE;"
    )
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not ensure customization tables: {e}")

@app.route('/api/customization-groups', methods=['GET', 'POST', 'OPTIONS'])
@cross_origin()
def customization_groups_collection():
    if request.method == 'GET':
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM customization_groups ORDER BY name;")
        groups = cur.fetchall()
        cur.execute("SELECT * FROM customization_options;")
        options = cur.fetchall()
        cur.close()
        conn.close()
        for g in groups:
            g['options'] = [o for o in options if o['group_id'] == g['id']]
        return jsonify(groups)

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    is_required = data.get('is_required', False)
    max_select = data.get('max_select')
    if not name:
        return jsonify({'error': 'name required'}), 400

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "INSERT INTO customization_groups (name, is_required, max_select) VALUES (%s, %s, %s) RETURNING *;",
            (name, is_required, max_select),
        )
        group = cur.fetchone()
        conn.commit()
    except pg_errors.UniqueViolation:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': 'Group exists'}), 409
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': str(e)}), 500

    cur.close()
    conn.close()
    group['options'] = []
    return jsonify(group), 201


@app.route('/api/customization-groups/<string:gid>', methods=['PUT', 'DELETE', 'OPTIONS'])
@cross_origin()
def customization_group_item(gid):
    if request.method == 'PUT':
        data = request.get_json() or {}
        fields, vals = [], []
        for key in ['name', 'is_required', 'max_select']:
            if key in data:
                fields.append(f"{key} = %s")
                vals.append(data[key])
        if not fields:
            return jsonify({'error': 'no data'}), 400
        vals.append(gid)
        sql = f"UPDATE customization_groups SET {', '.join(fields)}, updated_at = NOW() WHERE id = %s RETURNING *;"
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, tuple(vals))
        updated = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if updated:
            return jsonify(updated)
        return jsonify({'error': 'Group not found'}), 404

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("DELETE FROM customization_groups WHERE id = %s RETURNING id;", (gid,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if deleted:
        return jsonify({'id': deleted['id']})
    return jsonify({'error': 'Group not found'}), 404


@app.route('/api/customization-options', methods=['GET', 'POST', 'OPTIONS'])
@cross_origin()
def customization_options_collection():
    if request.method == 'GET':
        gid = request.args.get('group_id')
        sql = "SELECT * FROM customization_options"
        params = ()
        if gid:
            sql += " WHERE group_id = %s"
            params = (gid,)
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params)
        opts = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(opts)

    data = request.get_json() or {}
    gid = data.get('group_id')
    name = data.get('name', '').strip()
    extra = data.get('extra_price', 0)
    if not gid or not name:
        return jsonify({'error': 'group_id and name required'}), 400
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "INSERT INTO customization_options (group_id, name, extra_price) VALUES (%s, %s, %s) RETURNING *;",
        (gid, name, extra),
    )
    opt = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(opt), 201


@app.route('/api/customization-options/<string:oid>', methods=['PUT', 'DELETE', 'OPTIONS'])
@cross_origin()
def customization_option_item(oid):
    if request.method == 'PUT':
        data = request.get_json() or {}
        fields, vals = [], []
        for key in ['name', 'extra_price']:
            if key in data:
                fields.append(f"{key} = %s")
                vals.append(data[key])
        if not fields:
            return jsonify({'error': 'no data'}), 400
        vals.append(oid)
        sql = f"UPDATE customization_options SET {', '.join(fields)}, updated_at = NOW() WHERE id = %s RETURNING *;"
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, tuple(vals))
        updated = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if updated:
            return jsonify(updated)
        return jsonify({'error': 'Option not found'}), 404

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("DELETE FROM customization_options WHERE id = %s RETURNING id;", (oid,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if deleted:
        return jsonify({'id': deleted['id']})
    return jsonify({'error': 'Option not found'}), 404


@app.route('/api/menu-items/<string:item_id>/customizations', methods=['GET', 'PUT', 'OPTIONS'])
@cross_origin()
def menu_item_customizations_endpoint(item_id):
    if request.method == 'GET':
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT mic.id as mic_id, g.id, g.name, g.is_required, g.max_select,
                   json_agg(json_build_object(
                        'id', o.id,
                        'name', o.name,
                        'extra_price', o.extra_price,
                        'allowed', mico.id IS NOT NULL
                   ) ORDER BY o.name) AS options
            FROM menu_item_customizations mic
            JOIN customization_groups g ON g.id = mic.group_id
            JOIN customization_options o ON o.group_id = g.id
            LEFT JOIN menu_item_customization_options mico
                ON mico.item_id = mic.menu_item_id
                AND mico.option_id = o.id
            WHERE mic.menu_item_id = %s
            GROUP BY mic.id, g.id
            ORDER BY g.name;
            """,
            (item_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(rows)

    data = request.get_json() or {}
    groups = data.get('groups', [])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM menu_item_customization_options WHERE item_id = %s;",
        (item_id,),
    )
    cur.execute("DELETE FROM menu_item_customizations WHERE menu_item_id = %s;", (item_id,))
    for grp in groups:
        gid = grp.get('group_id')
        option_ids = grp.get('option_ids', [])
        cur.execute(
            "INSERT INTO menu_item_customizations (menu_item_id, group_id) VALUES (%s, %s) RETURNING id;",
            (item_id, gid),
        )
        mic_id = cur.fetchone()[0]
        for oid in option_ids:
            cur.execute(
                "INSERT INTO menu_item_customization_options (item_id, option_id) VALUES (%s, %s);",
                (item_id, oid),
            )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'status': 'ok'})

### Map Elements Endpoints ###
@app.route('/api/elements', methods=['GET'])
@cross_origin()
def get_elements():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM map_elements;")
    elems = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(elems)

@app.route('/api/elements', methods=['POST'])
@cross_origin()
def create_element():
    data = request.get_json() or {}
    columns, values, placeholders = [], [], []
    # Allow setting of type, section_id, position, size, rotation, content, and color
    for key in ['type','section_id','position_x','position_y','width','height','rotation','content','color','font_size','font_style']:
        if key in data:
            columns.append(key)
            values.append(data[key])
            placeholders.append('%s')
    if not columns:
        return jsonify({'error': 'No element data provided'}), 400
    sql = f"INSERT INTO map_elements ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    new_elem = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(new_elem), 201

@app.route('/api/elements/<string:elem_id>', methods=['PUT'])
@cross_origin()
def update_element(elem_id):
    data = request.get_json() or {}
    fields, values = [], []
    # Allow updating of type, section_id, position, size, rotation, content, and color
    for key in ['type','section_id','position_x','position_y','width','height','rotation','content','color','font_size','font_style']:
        if key in data:
            fields.append(f"{key} = %s")
            values.append(data[key])
    if not fields:
        return jsonify({'error': 'No valid fields provided'}), 400
    values.append(elem_id)
    sql = f"UPDATE map_elements SET {', '.join(fields)}, updated_at = NOW() WHERE id = %s RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if updated:
        return jsonify(updated)
    else:
        return jsonify({'error': 'Element not found'}), 404

@app.route('/api/elements/<string:elem_id>', methods=['DELETE'])
@cross_origin()
def delete_element(elem_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("DELETE FROM map_elements WHERE id = %s RETURNING id;", (elem_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if deleted:
        return jsonify({'id': deleted['id']})
    else:
        return jsonify({'error': 'Element not found'}), 404

@app.route('/ping', methods=['GET'])
def ping():
    """Health check endpoint returning a simple pong response."""
    return jsonify({"message": "pong"})
    
@app.route('/api/tables', methods=['GET'])
def get_tables():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM tables;")
    tables = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(tables)

@app.route('/api/tables/<string:table_id>', methods=['GET'])
def get_table(table_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM tables WHERE id = %s;", (table_id,))
    table = cur.fetchone()
    cur.close()
    conn.close()
    if table:
        return jsonify(table)
    else:
        return jsonify({"error": "Table not found"}), 404

@app.route('/api/tables/<string:table_id>', methods=['PUT'])
def update_table(table_id):
    data = request.get_json()
    fields = []
    values = []
    # Include 'shape' field for table shape support
    # Allow updating of table orientation and color in addition to existing fields
    for key in ['number', 'capacity', 'status', 'section_id', 'position_x', 'position_y', 'width', 'height', 'shape', 'rotation', 'color']:
        if key in data:
            fields.append(f"{key} = %s")
            values.append(data[key])
    if not fields:
        return jsonify({"error": "No valid fields provided"}), 400
    fields.append("updated_at = NOW()")
    sql = f"UPDATE tables SET {', '.join(fields)} WHERE id = %s RETURNING *;"
    values.append(table_id)
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if updated:
        return jsonify(updated)
    else:
        return jsonify({"error": "Table not found"}), 404

@app.route('/api/tables', methods=['POST'])
def create_table():
    data = request.get_json() or {}
    columns, values, placeholders = [], [], []
    # Allow setting of rotation and color for new tables
    for key in ['number', 'capacity', 'status', 'section_id', 'position_x', 'position_y', 'width', 'height', 'shape', 'rotation', 'color']:
        if key in data:
            columns.append(key)
            values.append(data[key])
            placeholders.append('%s')
    if not columns:
        return jsonify({'error': 'No table data provided'}), 400
    sql = f"INSERT INTO tables ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    new_table = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(new_table), 201

@app.route('/api/tables/<string:table_id>', methods=['DELETE'])
def delete_table(table_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("DELETE FROM tables WHERE id = %s RETURNING id;", (table_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if deleted:
        return jsonify({'id': deleted['id']})
    else:
        return jsonify({'error': 'Table not found'}), 404

@app.route('/api/menu', methods=['GET'])
@cross_origin()
def get_menu():
    """Return all menu items along with their category relation."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        """
        SELECT mi.*, mc.name AS category_name
        FROM menu_items mi
        JOIN menu_categories mc ON mc.id = mi.category_id
        ORDER BY mc.name, mi.name;
        """
    )
    items = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(items)
    
@app.route('/api/menu', methods=['POST', 'OPTIONS'])
@cross_origin()
def create_menu_item():
    data = request.get_json()
    columns, values, placeholders = [], [], []
    for key in ['name', 'price', 'category_id', 'subcategory_id', 'image', 'is_active']:
        if key in data:
            columns.append(key)
            values.append(data[key])
            placeholders.append('%s')
    if not columns:
        return jsonify({'error': 'No menu item data provided'}), 400
    sql = f"INSERT INTO menu_items ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    new_item = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(new_item), 201

@app.route('/api/menu/<string:item_id>', methods=['PUT', 'PATCH', 'DELETE', 'OPTIONS'])
@cross_origin()
def modify_menu_item(item_id):
    if request.method == 'PUT' or request.method == 'PATCH':
        data = request.get_json() or {}
        fields, values = [], []
        for key in ['name', 'price', 'category_id', 'subcategory_id', 'image', 'is_active']:
            if key in data:
                fields.append(f"{key} = %s")
                values.append(data[key])
        if not fields:
            return jsonify({'error': 'No menu item data provided'}), 400
        values.append(item_id)
        sql = f"UPDATE menu_items SET {', '.join(fields)}, updated_at = NOW() WHERE id = %s RETURNING *;"
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, tuple(values))
        updated = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if updated:
            return jsonify(updated)
        else:
            return jsonify({'error': 'Menu item not found'}), 404
    else:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("DELETE FROM menu_items WHERE id = %s RETURNING id;", (item_id,))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if deleted:
            return jsonify({'id': deleted['id']})
        else:
            return jsonify({'error': 'Menu item not found'}), 404

@app.route('/api/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    columns = []
    values = []
    placeholders = []
    for key in ['table_number', 'server', 'status', 'subtotal', 'tax', 'tip', 'total', 'discount_type', 'discount_value', 'payment_method', 'paid', 'client_count']:
        if key in data:
            columns.append(key)
            values.append(data[key])
            placeholders.append('%s')
    if not columns:
        return jsonify({"error": "No order data provided"}), 400
    sql = f"INSERT INTO orders ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    new_order = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(new_order), 201
    
@app.route('/api/orders', methods=['GET'])
def list_orders():
    """
    Retrieve all orders.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM orders;")
    orders = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(orders)

@app.route('/api/orders/<string:order_id>', methods=['GET'])
def get_order(order_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM orders WHERE id = %s;", (order_id,))
    order = cur.fetchone()
    cur.close()
    conn.close()
    if order:
        return jsonify(order)
    else:
        return jsonify({"error": "Order not found"}), 404

@app.route('/api/orders/<string:order_id>', methods=['PUT'])
def update_order(order_id):
    data = request.get_json()
    fields = []
    values = []
    for key in ['status', 'payment_method', 'paid']:
        if key in data:
            fields.append(f"{key} = %s")
            values.append(data[key])
    if not fields:
        return jsonify({"error": "No valid fields provided"}), 400
    fields.append("updated_at = NOW()")
    sql = f"UPDATE orders SET {', '.join(fields)} WHERE id = %s RETURNING *;"
    values.append(order_id)
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if updated:
        return jsonify(updated)
    else:
        return jsonify({"error": "Order not found"}), 404

@app.route('/api/order-items/<string:order_id>', methods=['GET'])
def get_order_items(order_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM order_items WHERE order_id = %s;", (order_id,))
    items = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(items)

@app.route('/api/order-items', methods=['POST'])
def create_order_item():
    data = request.get_json()
    columns = []
    values = []
    placeholders = []
    for key in ['order_id', 'menu_item_id', 'quantity', 'price', 'notes', 'client_number']:
        if key in data:
            columns.append(key)
            values.append(data[key])
            placeholders.append('%s')
    if not columns:
        return jsonify({"error": "No order item data provided"}), 400
    sql = f"INSERT INTO order_items ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(values))
    new_item = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify(new_item), 201

# Employee collection endpoints
@app.route('/api/employees', methods=['GET', 'POST', 'OPTIONS'])
@cross_origin()
def employees():
    """
    GET: List all employees.
    POST: Create a new employee.
    """
    if request.method == 'GET':
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM employees;")
        employees = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(employees)
    else:
        # Create new employee
        data = request.get_json() or {}
        fields = []
        values = []
        placeholders = []
        for key in ['name', 'position', 'status', 'hourly_rate']:
            if key in data:
                fields.append(key)
                values.append(data[key])
                placeholders.append('%s')
        if not fields:
            return jsonify({'error': 'No employee data provided'}), 400
        sql = f"INSERT INTO employees ({', '.join(fields)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, tuple(values))
        new_emp = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(new_emp), 201

# Endpoint to get, update, or delete a single employee by id
@app.route('/api/employees/<string:employee_id>', methods=['GET', 'PUT', 'DELETE', 'OPTIONS'])
@cross_origin()
def employee_item(employee_id):
    """CRUD operations for a single employee record."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == 'GET':
        # Fetch employee by id
        cur.execute("SELECT * FROM employees WHERE id = %s;", (employee_id,))
        employee = cur.fetchone()
        cur.close()
        conn.close()
        if employee:
            return jsonify(employee)
        return jsonify({'error': 'Employee not found'}), 404

    elif request.method == 'PUT':
        data = request.get_json() or {}

        # Accept only known columns to avoid SQL errors / injection
        allowed_fields = [
            'name', 'position', 'status', 'hourly_rate', 'clock_in',
            'clock_out', 'break_start', 'break_end', 'access_code'
        ]

        fields, values = [], []
        for key in allowed_fields:
            if key in data:
                fields.append(f"{key} = %s")
                values.append(data[key])

        if not fields:
            cur.close()
            conn.close()
            return jsonify({'error': 'No valid fields provided'}), 400

        # Always update the timestamp
        fields.append('updated_at = NOW()')

        # Build and execute the update query
        values.append(employee_id)
        sql = f"UPDATE employees SET {', '.join(fields)} WHERE id = %s RETURNING *;"
        try:
            cur.execute(sql, tuple(values))
            updated = cur.fetchone()
            conn.commit()
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({'error': str(e)}), 500

        cur.close()
        conn.close()

        if updated:
            return jsonify(updated)
        return jsonify({'error': 'Employee not found'}), 404

    else:  # DELETE
        try:
            cur.execute("DELETE FROM employees WHERE id = %s RETURNING id;", (employee_id,))
            deleted = cur.fetchone()
            conn.commit()
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({'error': str(e)}), 500

        cur.close()
        conn.close()

        if deleted:
            return jsonify({'id': deleted['id']})
        return jsonify({'error': 'Employee not found'}), 404

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM inventory_items;")
    inventory = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(inventory)

@app.route('/api/inventory_items/<string:item_id>', methods=['PUT', 'DELETE'])
def modify_inventory_item(item_id):
    """
    PUT: update an existing inventory item.
    DELETE: delete an inventory item.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if request.method == 'PUT':
        data = request.get_json() or {}
        fields = []
        values = []
        for key in ['name', 'supplier', 'quantity', 'unit', 'cost', 'image']:
            if key in data:
                fields.append(f"{key} = %s")
                values.append(data[key])
        if not fields:
            cur.close()
            conn.close()
            return jsonify({'error': 'No data provided'}), 400
        # Update timestamp
        fields.append('updated_at = NOW()')
        sql = f"UPDATE inventory_items SET {', '.join(fields)} WHERE id = %s RETURNING *;"
        values.append(item_id)
        try:
            cur.execute(sql, tuple(values))
            updated = cur.fetchone()
            conn.commit()
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({'error': str(e)}), 500
        cur.close()
        conn.close()
        if updated:
            return jsonify(updated)
        return jsonify({'error': 'Item not found'}), 404
    else:
        # DELETE
        try:
            cur.execute("DELETE FROM inventory_items WHERE id = %s RETURNING id;", (item_id,))
            deleted = cur.fetchone()
            conn.commit()
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            return jsonify({'error': str(e)}), 500
        cur.close()
        conn.close()
        if deleted:
            return jsonify({'id': deleted['id']})
        return jsonify({'error': 'Item not found'}), 404

@app.route('/api/inventory_items', methods=['POST'])
def create_inventory_item():
    """
    Create a new inventory item.
    Expected JSON body: { name, supplier, quantity, unit, cost, image? }
    """
    data = request.get_json() or {}
    # Validate required fields
    required = ['name', 'quantity', 'unit', 'cost']
    missing = [f for f in required if f not in data or data.get(f) is None]
    if missing:
        return jsonify({ 'error': f'Missing fields: {", ".join(missing)}' }), 400
    # Prepare columns and values
    cols = ['name', 'quantity', 'unit', 'cost']
    vals = [ data['name'], data['quantity'], data['unit'], data['cost'] ]
    # Optional fields
    if 'supplier' in data:
        cols.append('supplier')
        vals.append(data['supplier'])
    if 'image' in data:
        cols.append('image')
        vals.append(data['image'])
    # Use default created_at
    placeholders = ['%s'] * len(cols)
    sql = f"INSERT INTO inventory_items ({', '.join(cols)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(sql, tuple(vals))
        new_item = cur.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({ 'error': str(e) }), 500
    cur.close()
    conn.close()
    return jsonify(new_item), 201

# Restaurant sections endpoints
@app.route('/api/sections', methods=['GET', 'POST'])
def sections():
    if request.method == 'GET':
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM restaurant_sections ORDER BY name;")
        sections = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(sections)
    else:
        # Create new section
        data = request.get_json()
        name = data.get('name')
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "INSERT INTO restaurant_sections (name) VALUES (%s) RETURNING *;",
            (name,)
        )
        new_section = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(new_section), 201

@app.route('/api/sections/<string:section_id>', methods=['PUT', 'DELETE'])
def modify_section(section_id):
    if request.method == 'PUT':
        data = request.get_json()
        name = data.get('name')
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "UPDATE restaurant_sections SET name = %s, updated_at = NOW() WHERE id = %s RETURNING *;",
            (name, section_id)
        )
        updated = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if updated:
            return jsonify(updated)
        else:
            return jsonify({'error': 'Section not found'}), 404
    else:
        # DELETE
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM restaurant_sections WHERE id = %s RETURNING id;", (section_id,))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if deleted:
            return jsonify({'id': deleted[0]})
        else:
            return jsonify({'error': 'Section not found'}), 404

# Create and delete table endpoints
@app.route('/api/tables', methods=['GET', 'POST'])
def tables_collection():
    if request.method == 'GET':
        # existing get_tables logic
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM tables;")
        tables = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(tables)
    else:
        # Create new table
        data = request.get_json()
        # Expect fields: number, capacity, status, section_id, position_x, position_y, width, height, shape
        columns = []
        values = []
        placeholders = []
        # Include 'shape' to store table shape
        for key in ['number','capacity','status','section_id','position_x','position_y','width','height','shape']:
            if key in data:
                columns.append(key)
                values.append(data[key])
                placeholders.append('%s')
        if not columns:
            return jsonify({'error':'No valid fields provided'}),400
        sql = f"INSERT INTO tables ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *;"
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, tuple(values))
        new_table = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(new_table), 201

@app.route('/api/tables/<string:table_id>', methods=['GET', 'PUT', 'DELETE'])
def table_item(table_id):
    if request.method == 'GET':
        return get_table(table_id)
    elif request.method == 'PUT':
        return update_table(table_id)
    else:
        # DELETE table
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("DELETE FROM tables WHERE id = %s RETURNING id;", (table_id,))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if deleted:
            return jsonify({'id': deleted['id']})
        else:
            return jsonify({'error':'Table not found'}),404

# Break history endpoints
@app.route('/api/break-history', methods=['GET', 'POST'])
def break_history_collection():
    if request.method == 'GET':
        employee_id = request.args.get('employee_id')
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if employee_id:
            cur.execute(
                "SELECT * FROM break_history WHERE employee_id = %s ORDER BY break_start DESC;",
                (employee_id,)
            )
        else:
            cur.execute("SELECT * FROM break_history ORDER BY break_start DESC;")
        records = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify(records)
    else:
        data = request.get_json()
        cols, vals, ph = [], [], []
        for key in ['employee_id','break_start','break_end','date']:
            if key in data:
                cols.append(key)
                vals.append(data[key])
                ph.append('%s')
        if not cols:
            return jsonify({'error':'No data provided'}),400
        sql = f"INSERT INTO break_history ({', '.join(cols)}) VALUES ({', '.join(ph)}) RETURNING *;"
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, tuple(vals))
        new_record = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(new_record),201

@app.route('/api/break-history/<string:record_id>', methods=['PUT'])
def break_history_item(record_id):
    data = request.get_json()
    fields, vals = [], []
    for key in ['employee_id','break_start','break_end','date']:
        if key in data:
            fields.append(f"{key} = %s")
            vals.append(data[key])
    if not fields:
        return jsonify({'error':'No data provided'}),400
    vals.append(record_id)
    sql = f"UPDATE break_history SET {', '.join(fields)} WHERE id = %s RETURNING *;"
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, tuple(vals))
    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if updated:
        return jsonify(updated)
    else:
        return jsonify({'error':'Record not found'}),404

# Seed mock data for menu_items and inventory_items if tables are empty
try:
    conn = get_db_connection()
    cur = conn.cursor()
    # Menu items
    cur.execute("SELECT COUNT(*) FROM menu_items;")
    if cur.fetchone()[0] == 0:
        # Seed some mock menu items across Breakfast, Lunch, Dinner
        mock_menu = [
            ('Pancakes', 5.99, 'Breakfast', 'pancakes.png'),
            ('Omelette', 6.49, 'Breakfast', 'omelette.png'),
            ('Coffee', 2.50, 'Breakfast', 'coffee.png'),
            ('BLT Sandwich', 7.50, 'Lunch', 'blt_sandwich.png'),
            ('Caesar Salad', 8.00, 'Lunch', 'caesar_salad.png'),
            ('Burger', 9.25, 'Lunch', 'burger.png'),
            ('Steak Dinner', 15.00, 'Dinner', 'steak_dinner.png'),
            ('Grilled Salmon', 14.50, 'Dinner', 'grilled_salmon.png'),
            ('Ice Cream', 4.00, 'Dessert', 'ice_cream.png')
        ]
        for name, price, category, image in mock_menu:
            cur.execute(
                "INSERT INTO menu_items (name, price, category, image) VALUES (%s, %s, %s, %s);",
                (name, price, category, image)
            )
    # Inventory items
    cur.execute("SELECT COUNT(*) FROM inventory_items;")
    if cur.fetchone()[0] == 0:
        mock_inv = [
            ('Coffee Beans', 20, 'kg', 15.0, 'Local Supplier', None),
            ('Milk', 10, 'liters', 1.2, 'Dairy Co', None),
            ('Bread Loaf', 30, 'pcs', 0.5, 'Bakery Inc', None),
            ('Lettuce', 25, 'heads', 0.8, 'Green Farms', None)
        ]
        for name, quantity, unit, cost, supplier, image in mock_inv:
            cur.execute(
                "INSERT INTO inventory_items (name, quantity, unit, cost, supplier, image) VALUES (%s, %s, %s, %s, %s, %s);",
                (name, quantity, unit, cost, supplier, image)
            )
    # Seed owner employee if none exist
    cur.execute("SELECT COUNT(*) FROM employees;")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO employees (name, position, status, hourly_rate, access_code) VALUES (%s, %s, %s, %s, %s);",
            ("Carlos Flores", "owner", "active", 0, "1020304")
        )
    conn.commit()
    cur.close()
    conn.close()
except Exception as e:
    print(f"Warning: could not seed mock data: {e}")

if __name__ == '__main__':
    import os
    port = int(os.getenv('FLASK_PORT', '5050'))  # usa 5050 por defecto si no existe FLASK_PORT
    app.run(host='0.0.0.0', port=port, debug=True)
