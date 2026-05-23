#!/usr/bin/env node
const crypto = require('crypto')

const alphabet = '0123456789abcdefghijklmnopqrstuvwxyz'

function toBase36(buffer) {
  let value = BigInt('0x' + buffer.toString('hex'))
  if (value === 0n) return '0'
  let output = ''
  while (value > 0n) {
    output = alphabet[Number(value % 36n)] + output
    value = value / 36n
  }
  return output
}

function createChartComponentId(length = 14) {
  const randomBytes = crypto.randomBytes(10)
  const timestampBytes = Buffer.allocUnsafe(6)
  timestampBytes.writeUIntBE(Date.now(), 0, 6)
  const digest = crypto
    .createHash('sha256')
    .update(timestampBytes)
    .update(randomBytes)
    .digest()
  return `id_${toBase36(digest).slice(0, length)}`
}

if (require.main === module) {
  const count = Number(process.argv[2] || 1)
  for (let index = 0; index < count; index += 1) {
    console.log(createChartComponentId())
  }
}

module.exports = { createChartComponentId }