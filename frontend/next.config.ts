import { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // standalone es para Docker; en Vercel no hace falta y puede interferir
  ...(process.env.VERCEL ? {} : { output: "standalone" as const }),
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
