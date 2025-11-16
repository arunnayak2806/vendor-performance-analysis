import os
import sqlite3
import pandas as pd
import logging
from ingestion_db import ingest_db

# -----------------------------------------------------------
# Ensure logs directory exists
# -----------------------------------------------------------
os.makedirs("logs", exist_ok=True)
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Define log file path
LOG_FILE = os.path.join(LOG_DIR, "get_vendor_summary.log")

# Remove any existing handlers to avoid conflicts (especially in VS Code or Jupyter)
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# -----------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------
logging.basicConfig(
    filename="logs/get_vendor_summary.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filemode="a"
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console.setFormatter(formatter)
logging.getLogger().addHandler(console)

logging.info("✅ Logging initialized successfully.")
# -----------------------------------------------------------
# Function: Create Vendor Summary
# -----------------------------------------------------------
def create_vendor_summary(conn):
    """
    This function merges different tables to get the overall vendor summary
    and adds new columns in the resultant data.
    """
    vendor_sales_summary = pd.read_sql_query("""
    WITH FreightSummary AS (
        SELECT 
            VendorNumber,
            SUM(Freight) AS FreightCost
        FROM vendor_invoice
        GROUP BY VendorNumber
    ),
    PurchaseSummary AS (
        SELECT
            p.VendorNumber,
            p.VendorName,
            p.Brand,
            p.Description,
            p.PurchasePrice,
            pp.Price AS ActualPrice,
            pp.Volume,
            SUM(p.Quantity) AS TotalPurchaseQuantity,
            SUM(p.Dollars) AS TotalPurchaseDollars
        FROM purchases p
        JOIN purchase_prices pp
            ON p.Brand = pp.Brand
        WHERE p.PurchasePrice > 0
        GROUP BY 
            p.VendorNumber, p.VendorName, p.Brand, p.Description, 
            p.PurchasePrice, pp.Price, pp.Volume
    ),
    SalesSummary AS (
        SELECT
            VendorNo,
            Brand,
            SUM(SalesQuantity) AS TotalSalesQuantity,
            SUM(SalesDollars) AS TotalSalesDollars,
            SUM(SalesPrice) AS TotalSalesPrice,
            SUM(ExciseTax) AS TotalExciseTax
        FROM sales
        GROUP BY VendorNo, Brand
    )
    SELECT
        ps.VendorNumber,
        ps.VendorName,
        ps.Brand,
        ps.Description,
        ps.PurchasePrice,
        ps.ActualPrice,
        ps.Volume,
        ps.TotalPurchaseQuantity,
        ps.TotalPurchaseDollars,
        ss.TotalSalesQuantity,
        ss.TotalSalesDollars,
        ss.TotalSalesPrice,
        ss.TotalExciseTax,
        fs.FreightCost
    FROM PurchaseSummary ps
    LEFT JOIN SalesSummary ss
        ON ps.VendorNumber = ss.VendorNo
        AND ps.Brand = ss.Brand
    LEFT JOIN FreightSummary fs
        ON ps.VendorNumber = fs.VendorNumber
    ORDER BY ps.TotalPurchaseDollars DESC
    """, conn)

    return vendor_sales_summary


# -----------------------------------------------------------
# Function: Clean and Prepare Data
# -----------------------------------------------------------
def clean_data(df):
    # This function will clean and prepare the vendor_sales_summary data"""

    # Change datatype to float
    df['Volume'] = df['Volume'].astype(float)

    # Fill missing values with 0
    df.fillna(0, inplace=True)

    # Remove spaces from categorical columns
    df['VendorName'] = df['VendorName'].str.strip()
    df['Description'] = df['Description'].str.strip()

    # Create new analytical columns
    df['GrossProfit'] = df['TotalSalesDollars'] - df['TotalPurchaseDollars']
    df['ProfitMargin'] = (df['GrossProfit'] / df['TotalSalesDollars'].replace(0, 1)) * 100
    df['StockTurnover'] = df['TotalSalesQuantity'] / df['TotalPurchaseQuantity'].replace(0, 1)
    df['SalesToPurchaseRatio'] = df['TotalSalesDollars'] / df['TotalPurchaseDollars'].replace(0, 1)

    return df


# -----------------------------------------------------------
# Main Execution
# -----------------------------------------------------------
if __name__ == '__main__':
    # Create database connection
    conn = sqlite3.connect('inventory.db')

    logging.info('Creating Vendor Summary Table...')
    summary_df = create_vendor_summary(conn)
    logging.info(f"Sample Summary Data:\n{summary_df.head()}")

    logging.info('Cleaning Data...')
    clean_df = clean_data(summary_df)
    logging.info(f"Sample Cleaned Data:\n{clean_df.head()}")

    logging.info('Ingesting data into database...')
    ingest_db(clean_df, 'vendor_sales_summary', conn)

    logging.info('✅ Process Completed Successfully.')
    conn.close()
