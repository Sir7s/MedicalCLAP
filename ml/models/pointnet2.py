"""PointNet++ CT encoder (P11, SPEC-07 §8.2).

Hierarchical set-abstraction encoder: farthest-point sampling selects centroids,
kNN grouping forms local regions, a shared MLP + max-pool summarizes each region,
and a final global MLP produces a 512-d L2-normalized embedding.

Input:  (B, N, 4) points = (x, y, z, density).
Output: (B, 512) L2-normalized embedding.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import Tensor, nn


def square_distance(a: Tensor, b: Tensor) -> Tensor:
    """(B, N, C), (B, M, C) -> (B, N, M) pairwise squared distances."""
    return torch.cdist(a, b) ** 2


def index_points(points: Tensor, idx: Tensor) -> Tensor:
    """Gather points by index. points (B,N,C), idx (B,S[,K]) -> (B,S[,K],C)."""
    b = points.shape[0]
    view = [b] + [1] * (idx.dim() - 1)
    batch = torch.arange(b, device=points.device).view(view).expand_as(idx)
    return points[batch, idx]


def farthest_point_sample(xyz: Tensor, npoint: int) -> Tensor:
    """Iterative FPS. xyz (B,N,3) -> centroid indices (B, npoint)."""
    b, n, _ = xyz.shape
    device = xyz.device
    centroids = torch.zeros(b, npoint, dtype=torch.long, device=device)
    distance = torch.full((b, n), 1e10, device=device)
    farthest = torch.zeros(b, dtype=torch.long, device=device)  # deterministic start
    batch = torch.arange(b, device=device)
    for i in range(npoint):
        centroids[:, i] = farthest
        centroid = xyz[batch, farthest].unsqueeze(1)          # (B,1,3)
        dist = ((xyz - centroid) ** 2).sum(-1)                 # (B,N)
        distance = torch.minimum(distance, dist)
        farthest = distance.argmax(-1)
    return centroids


def knn(xyz: Tensor, new_xyz: Tensor, k: int) -> Tensor:
    """k nearest neighbors. -> (B, S, k) indices into xyz."""
    dists = square_distance(new_xyz, xyz)                      # (B,S,N)
    return dists.topk(k, dim=-1, largest=False).indices


class SetAbstraction(nn.Module):
    def __init__(self, npoint: int, k: int, in_channels: int, mlp: list[int]):
        super().__init__()
        self.npoint = npoint
        self.k = k
        layers: list[nn.Module] = []
        c = in_channels + 3  # + relative xyz
        for out in mlp:
            layers += [nn.Conv2d(c, out, 1), nn.BatchNorm2d(out), nn.ReLU()]
            c = out
        self.mlp = nn.Sequential(*layers)

    def forward(self, xyz: Tensor, feat: Tensor | None) -> tuple[Tensor, Tensor]:
        idx = farthest_point_sample(xyz, self.npoint)
        new_xyz = index_points(xyz, idx)                       # (B,S,3)
        group_idx = knn(xyz, new_xyz, self.k)                  # (B,S,k)
        grouped_xyz = index_points(xyz, group_idx) - new_xyz.unsqueeze(2)
        if feat is not None:
            grouped_feat = index_points(feat, group_idx)
            grouped = torch.cat([grouped_xyz, grouped_feat], dim=-1)
        else:
            grouped = grouped_xyz
        # (B,S,k,C) -> (B,C,k,S) for Conv2d
        x = grouped.permute(0, 3, 2, 1).contiguous()
        x = self.mlp(x)
        new_feat = x.max(dim=2).values.permute(0, 2, 1).contiguous()  # (B,S,C')
        return new_xyz, new_feat


class PointNet2Encoder(nn.Module):
    def __init__(self, out_dim: int = 512):
        super().__init__()
        self.sa1 = SetAbstraction(npoint=256, k=16, in_channels=1, mlp=[32, 32, 64])
        self.sa2 = SetAbstraction(npoint=64, k=16, in_channels=64, mlp=[64, 64, 128])
        self.head = nn.Sequential(
            nn.Linear(128, 256), nn.BatchNorm1d(256), nn.ReLU(),
            nn.Linear(256, out_dim),
        )

    def forward(self, points: Tensor) -> Tensor:
        xyz = points[..., :3].contiguous()
        feat = points[..., 3:].contiguous()  # density (B,N,1)
        xyz, feat = self.sa1(xyz, feat)
        xyz, feat = self.sa2(xyz, feat)
        global_feat = feat.max(dim=1).values   # (B,128)
        emb = self.head(global_feat)
        return F.normalize(emb, dim=-1)
