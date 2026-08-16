import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from agentic_chatbot_hitl_backend import ingest_rag_document

from .. import schemas

router = APIRouter(
    prefix="/ingest",
    tags=['Ingest']
)


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.IngestOut)
def ingest_pdf(file: UploadFile = File(...)):
    """上传 PDF 并建立向量索引（供 rag_tool 检索）。"""
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="只支持 PDF 文件",
        )

    temp_path = None
    try:

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf"
        ) as temp_file:

            temp_file.write(file.file.read())
            temp_path = temp_file.name

        ingest_rag_document(temp_path)

        return {"message": f"{file.filename} 处理成功"}

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF 处理失败: {error}",
        )

    finally:
        # 处理完成后删除临时 PDF 文件
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
