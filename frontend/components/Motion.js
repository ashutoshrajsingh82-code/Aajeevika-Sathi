'use client';
import {motion,MotionConfig} from 'framer-motion';
export function MotionDiv({children,...props}){return <MotionConfig reducedMotion="user"><motion.div initial={{opacity:0,y:10}} animate={{opacity:1,y:0}} transition={{duration:.35}} {...props}>{children}</motion.div></MotionConfig>}
