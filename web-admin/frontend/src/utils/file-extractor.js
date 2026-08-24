let pdfjsPromise
let mammothPromise
let xlsxPromise

function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import('pdfjs-dist/legacy/build/pdf.mjs').then((pdfjsLib) => {
      pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.mjs`
      return pdfjsLib
    })
  }
  return pdfjsPromise
}

function loadMammoth() {
  if (!mammothPromise) {
    mammothPromise = import('mammoth').then((module) => module.default)
  }
  return mammothPromise
}

function loadXlsx() {
  if (!xlsxPromise) {
    xlsxPromise = import('xlsx')
  }
  return xlsxPromise
}

export async function extractTextFromFile(file) {
  if (!file) return ''

  const name = file.name.toLowerCase()
  try {
    if (name.endsWith('.txt') || name.endsWith('.csv') || name.endsWith('.md')) {
      return await file.text()
    }

    if (name.endsWith('.pdf')) {
      const pdfjsLib = await loadPdfjs()
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
      const mammoth = await loadMammoth()
      const arrayBuffer = await file.arrayBuffer()
      const result = await mammoth.extractRawText({ arrayBuffer })
      return result.value.trim()
    }

    if (name.endsWith('.xlsx') || name.endsWith('.xls')) {
      const XLSX = await loadXlsx()
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
