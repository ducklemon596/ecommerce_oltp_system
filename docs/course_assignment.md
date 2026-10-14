# Project 04 - SQL

## **1. Optimization techniques**

- Write query for listing requirement and snapshot the result (run time and execution plan)
    - Total revenue per month
    - Orders filtered by seller and date
    - Filter data in `order_item` by product_id
    - Find order with highest total_amount
    - List products with highest quantity sold
    - Orders by Seller in March 2025
    - Revenue per Product per Month
    - Products Sold per Seller
- Create monthly partitions (Jan–May 2025) for the two tables above and create an index on the `product_id` column of `order_item` table.
    - 💡 **Hint (PostgreSQL):**
        
        If you encounter the error `ERROR: unique constraint on partitioned table must include all partitioning columns`, remember that in PostgreSQL declarative partitioning, the partition key must be part of the Primary Key constraint! Think about composite primary keys `(order_id, order_date)`.
        
- Re-run the queries for the requirements above and take a snapshot of the results. Compare the detailed execution plans before and after optimization.

## **2. Making dynamic report (using function, procedure)**

<aside>
💡

Select only the required columns.
Include business-relevant calculations (total revenue, quantity sold, number of orders, etc.)
Include filters (date range, seller, brand, category, customer, etc.)
Be optimized for performance (consider indexes and partitions if available).

</aside>

### **Monthly Revenue Report**

- **Goal:** Show total revenue and total orders per month.
- **Columns:** `month`, `total_orders`, `total_quantity`, `total_revenue`
- **Filter:** Orders within a specific date range (`start_date` to `end_date`)

### **Daily Revenue Report**

- **Goal:** Show total revenue and total orders per day.
- **Columns:** `date`, `total_orders`, `total_quantity`, `total_revenue`
- **Filter:** Orders within a specific date range (`start_date` to `end_date`) and *product list*

### **Seller Performance Report**

- **Goal:** Compare sellers by total revenue and quantity sold.
- **Columns:** `seller_id`, `seller_name`, `total_orders`, `total_quantity`, `total_revenue`
- **Filter:** Orders within a specific date range. Optional filter by `category_id` or `brand_id`.

### **Top Products per Brand**

- **Goal:** Identify top products for each brand by quantity sold.
- **Columns:** `brand_id`, `brand_name`, `product_id`, `product_name`, `total_quantity`, `total_revenue`
- **Filter:** Orders within a specific date range. Optional filter by *seller list.*

### **Orders Status Summary**

- **Goal:** Count orders per status (completed, pending, cancelled).
- **Columns:** `status`, `total_orders`, `total_revenue`
- **Filter:** Orders within a specific date range; optionally filter by seller list or category list.

💡 If you're unsure or don't fully understand the requirements, please **contact Duy Nguyen directly** for clarification.
