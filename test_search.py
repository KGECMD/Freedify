import asyncio
import sys

from app.audiobookbay_service import search_audiobooks

async def main():
    try:
        res = await search_audiobooks('Yanis Varoufakis')
        print(f"Success! Found {len(res)} results.")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
