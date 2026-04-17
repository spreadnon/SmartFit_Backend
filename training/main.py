import uvicorn
from api import app  # 导入FastAPI应用

if __name__ == "__main__":
    import uvicorn
    # 启动服务
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8001, 
        reload=False, 
        proxy_headers=True, 
        forwarded_allow_ips="*"
    )