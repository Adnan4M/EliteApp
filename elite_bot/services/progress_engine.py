def calculate_percentage(done, total):
    if total == 0:
        return 0
    return int((done / total) * 100)
