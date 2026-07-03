import asyncio
from backend.modules.crm.service.pipedrive_service import pipedrive_service

async def main():
    print("Fetching activities...")
    resp = await pipedrive_service._request("GET", "activities", params={"user_id": pipedrive_service.user_id, "limit": 500, "done": 0})
    
    if resp is None or resp.status_code != 200:
        print("Failed to fetch")
        return
        
    data = resp.json().get("data") or []
    print(f"Total pending tasks: {len(data)}")
    
    overdue = 0
    today = 0
    future = 0
    
    from datetime import datetime, timezone, timedelta
    sao_paulo_tz = timezone(timedelta(hours=-3))
    today_date = datetime.now(sao_paulo_tz).date().isoformat()
    
    for task in data:
        due = task.get("due_date")
        if not due:
            continue
        if due < today_date:
            overdue += 1
        elif due == today_date:
            today += 1
        else:
            future += 1
            
    print(f"Overdue: {overdue}")
    print(f"Today: {today}")
    print(f"Future: {future}")

if __name__ == "__main__":
    asyncio.run(main())
