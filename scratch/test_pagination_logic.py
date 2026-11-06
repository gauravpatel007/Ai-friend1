import math

def calculate_pagination(page: int, page_size: int, total_results: int, tmdb_page_size: int = 20):
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    first_tmdb_page = (start_idx // tmdb_page_size) + 1
    last_tmdb_page = ((end_idx - 1) // tmdb_page_size) + 1

    # offset in the collected items
    slice_start = start_idx - (first_tmdb_page - 1) * tmdb_page_size
    slice_end = slice_start + page_size

    total_pages = max(1, math.ceil(total_results / page_size)) if total_results > 0 else 1

    return {
        "start_idx": start_idx,
        "end_idx": end_idx,
        "first_tmdb_page": first_tmdb_page,
        "last_tmdb_page": last_tmdb_page,
        "slice_start": slice_start,
        "slice_end": slice_end,
        "total_pages": total_pages,
    }

print("Page 1 (50 per page):", calculate_pagination(1, 50, 1000))
print("Page 2 (50 per page):", calculate_pagination(2, 50, 1000))
print("Page 3 (50 per page):", calculate_pagination(3, 50, 1000))
print("Page 4 (50 per page):", calculate_pagination(4, 50, 1000))
print("Page 5 (50 per page):", calculate_pagination(5, 50, 1000))

# Test that items from page 1 and page 2 are contiguous with 0 gaps and 0 duplicates:
mock_db = [f"movie_{i}" for i in range(1, 1001)]

def get_page_items(page: int, page_size: int):
    info = calculate_pagination(page, page_size, len(mock_db))
    collected = []
    for tp in range(info["first_tmdb_page"], info["last_tmdb_page"] + 1):
        # TMDB page tp
        tmdb_items = mock_db[(tp - 1) * 20 : tp * 20]
        collected.extend(tmdb_items)
    
    return collected[info["slice_start"] : info["slice_end"]]

p1 = get_page_items(1, 50)
p2 = get_page_items(2, 50)
p3 = get_page_items(3, 50)

print(f"\nP1 length: {len(p1)}, first: {p1[0]}, last: {p1[-1]}")
print(f"P2 length: {len(p2)}, first: {p2[0]}, last: {p2[-1]}")
print(f"P3 length: {len(p3)}, first: {p3[0]}, last: {p3[-1]}")

assert p1 == mock_db[0:50]
assert p2 == mock_db[50:100]
assert p3 == mock_db[100:150]
print("\nAssertion passed: Perfect contiguous indexing without duplicates or gaps!")
