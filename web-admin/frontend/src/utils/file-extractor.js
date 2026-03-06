import * as pdfjsLib from 'pdfjs-dist/legacy/build/pdf.mjs'
import mammoth from 'mammoth'
import * as XLSX from 'xlsx'

pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.mjs`

export async function extractTextFromFile(file) {
  if (!file) return ''

  const name = file.name.toLowerCase()
  try {
    if (name.endsWith('.txt') || name.endsWith('.csv') || name.endsWith('.md')) {
      return await file.text()
    }

    if (name.endsWith('.pdf')) {
      const arrayBuffer = await file.arrayBuffer()
      const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise
      let fullText = ''
      for (let i = 1; i <= pdf.numPages; i++) {
        const page = await pdf.getPage(i)
        const textContent = await page.getTextContent()
        const pageText = textContent.items.map(item => item.str).join(' ')
        fullText += pageText + '\n'
      }
      return fullText.trim()
    }

    if (name.endsWith('.docx') || name.endsWith('.wps')) {
      const arrayBuffer = await file.arrayBuffer()
      const result = await mammoth.extractRawText({ arrayBuffer })
      return result.value.trim()
    }

    if (name.endsWith('.xlsx') || name.endsWith('.xls')) {
      const arrayBuffer = await file.arrayBuffer()
      const workbook = XLSX.read(arrayBuffer, { type: 'buffer' })
      let fullText = ''
      for (const sheetName of workbook.SheetNames) {
        const worksheet = workbook.Sheets[sheetName]
        const csv = XLSX.utils.sheet_to_csv(worksheet)
        fullText += `--- Sheet: ${sheetName} ---\n${csv}\n\n`
      }
      return fullText.trim()
    }

    return ''
  } catch (err) {
    console.error(`Failed to extract text from ${file.name}:`, err)
    return `（无法读取文件内容: ${file.name}）`
  }
}
