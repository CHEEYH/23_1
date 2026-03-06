# ui/components/assembly_queue_manager.py

import json
import os
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class AssemblyStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    WAITING = "waiting_for_parts"
    PARTIAL = "partial"


class AssemblyJob:
    """单个装配作业"""

    def __init__(self, job_id, recipe_name, required_parts):
        self.job_id = job_id
        self.recipe_name = recipe_name
        self.required_parts = required_parts  # {"A":1, "B":1, "C":1}
        self.allocated_parts = {}
        self.completed_steps = []
        self.pending_steps = []
        self.skipped_steps = []
        self.status = AssemblyStatus.PENDING
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def to_dict(self):
        return {
            'job_id': self.job_id,
            'recipe_name': self.recipe_name,
            'required_parts': self.required_parts,
            'allocated_parts': self.allocated_parts,
            'completed_steps': self.completed_steps,
            'pending_steps': self.pending_steps,
            'skipped_steps': self.skipped_steps,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data):
        job = cls(data['job_id'], data['recipe_name'], data['required_parts'])
        job.allocated_parts = data.get('allocated_parts', {})
        job.completed_steps = data.get('completed_steps', [])
        job.pending_steps = data.get('pending_steps', [])
        job.skipped_steps = data.get('skipped_steps', [])
        job.status = AssemblyStatus(data['status'])
        job.created_at = datetime.fromisoformat(data['created_at'])
        job.updated_at = datetime.fromisoformat(data['updated_at'])
        return job


class AssemblyQueueManager:
    """管理装配队列"""

    def __init__(self, recipe_path):
        self.recipe_path = recipe_path
        self.jobs_file = os.path.join(recipe_path, 'assembly_queue.json')
        self.jobs = []
        self.load_jobs()

    def load_jobs(self):
        """加载作业"""
        if os.path.exists(self.jobs_file):
            try:
                with open(self.jobs_file, 'r') as f:
                    data = json.load(f)
                    self.jobs = [AssemblyJob.from_dict(j) for j in data]
            except:
                self.jobs = []

    def save_jobs(self):
        """保存作业"""
        try:
            with open(self.jobs_file, 'w') as f:
                json.dump([j.to_dict() for j in self.jobs], f, indent=2)
        except Exception as e:
            print(f"保存作业失败: {e}")

    def create_job(self, recipe_name, required_parts):
        """创建新作业"""
        job_id = f"JOB_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.jobs)}"
        job = AssemblyJob(job_id, recipe_name, required_parts)
        job.pending_steps = list(range(1, len(required_parts) + 1))
        self.jobs.append(job)
        self.save_jobs()
        return job

    def get_pending_jobs(self):
        """获取待处理的作业"""
        return [j for j in self.jobs if j.status == AssemblyStatus.PENDING]

    def get_waiting_jobs(self):
        """获取等待零件的作业"""
        return [j for j in self.jobs if j.status == AssemblyStatus.WAITING]

    def get_partial_jobs(self):
        """获取部分完成的作业"""
        return [j for j in self.jobs if j.status == AssemblyStatus.PARTIAL]

    def update_job_status(self, job_id, completed_step, skipped=False):
        """更新作业状态"""
        for job in self.jobs:
            if job.job_id == job_id:
                if skipped:
                    job.skipped_steps.append(completed_step)
                else:
                    job.completed_steps.append(completed_step)

                if completed_step in job.pending_steps:
                    job.pending_steps.remove(completed_step)

                job.updated_at = datetime.now()

                # 更新状态
                if not job.pending_steps:
                    job.status = AssemblyStatus.COMPLETED
                elif job.skipped_steps:
                    job.status = AssemblyStatus.PARTIAL

                self.save_jobs()
                return True
        return False