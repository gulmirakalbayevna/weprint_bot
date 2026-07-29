import asyncio

# Admin navbatiga kitob qo'shishda ("band/band emas" tekshiruvi) bir vaqtda
# ikkita foydalanuvchi bir xil holatga yozib qo'ymasligi uchun umumiy lock.
# Bu bot ichida bitta marta yaratiladi va barcha handlerlar shu bittasidan foydalanadi.
admin_queue_lock = asyncio.Lock()
